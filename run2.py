#!/usr/bin/env python3
"""
Simplified test server - Queue-based concurrent page loading
Uses camoufox_helper + CAPTCHA solving from ahrefs_helper
"""

import asyncio
import threading
import time
from datetime import datetime
import cv2
import numpy as np
from flask import Flask, jsonify, request
from camoufox_helper import (
    initialize_browser, 
    close_browser, 
    get_or_create_context, 
    create_page_in_context,
    get_context_pool_stats
)

app = Flask(__name__)

# Configuration
MAX_CONCURRENT_PROCESSING = 4  # Number of concurrent workers
DEBUG = False  # Set to True for verbose logging

# Queue and processing state
task_queue = []
current_processing_count = 0
processing_count_lock = threading.Lock()

# Global event loop and thread
global_loop = None
loop_thread = None

# Results storage
completed_tasks = []
failed_tasks = []


def parse_proxy(proxy_string):
    """Parse proxy string in format: ip:port:user:pass"""
    if not proxy_string:
        return None
    
    parts = proxy_string.split(':')
    if len(parts) >= 4:
        return {
            'server': f"http://{parts[0]}:{parts[1]}",
            'username': parts[2],
            'password': parts[3]
        }
    return None


async def extract_metrics(page):
    """Extract DR, backlinks, and linking websites from Ahrefs page"""
    metrics = await page.evaluate("""
        () => {
            let dr = null;
            let backlinks = null;
            let linkingWebsites = null;
            
            const allElements = Array.from(document.querySelectorAll('*'));
            
            const drLabel = allElements.find(el => el.textContent.trim() === 'Domain Rating');
            const backlinksLabel = allElements.find(el => el.textContent.trim() === 'Backlinks');
            const linkingLabel = allElements.find(el => el.textContent.trim() === 'Linking websites');
            
            const findNumber = (label) => {
                if (!label) return null;
                
                let parent = label;
                for (let i = 0; i < 8; i++) {
                    parent = parent.parentElement;
                    if (!parent) break;
                    
                    const spans = parent.querySelectorAll('span');
                    for (const span of spans) {
                        const text = span.textContent.trim();
                        const fontSize = window.getComputedStyle(span).fontSize;
                        
                        if (text && /^[0-9.,KM]+$/.test(text) && parseFloat(fontSize) > 25) {
                            return text;
                        }
                    }
                }
                return null;
            };
            
            dr = findNumber(drLabel);
            backlinks = findNumber(backlinksLabel);
            linkingWebsites = findNumber(linkingLabel);
            
            return {
                _dr: dr,
                backlinks: backlinks,
                linking_websites: linkingWebsites
            };
        }
    """)
    
    def convert_to_int(value):
        if not value:
            return None
        
        value = str(value).replace(',', '')
        
        if 'K' in value:
            return int(float(value.replace('K', '')) * 1000)
        elif 'M' in value:
            return int(float(value.replace('M', '')) * 1000000)
        else:
            return int(float(value))
    
    return {
        '_dr': convert_to_int(metrics['_dr']),
        'backlinks': convert_to_int(metrics['backlinks']),
        'linking_websites': convert_to_int(metrics['linking_websites'])
    }


async def find_and_click_captcha(page, captcha_type):
    """
    Find and click CAPTCHA checkbox using computer vision
    (EXACT COPY from server.py with 3 detection methods + scoring)
    
    Args:
        page: Playwright page object
        captcha_type: 'full_page' or 'main_page'
    
    Returns:
        bool: True if checkbox found and clicked, False otherwise
    """
    try:
        # Take screenshot
        screenshot_bytes = await page.screenshot()
        img_array = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        checkbox_candidates = []
        
        # METHOD 1: Color-based detection (look for white/light squares)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Create mask for white/light gray areas (checkbox is white)
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)
                    
        # Find contours in white mask
        contours_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours_white:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Checkbox size filter (18-32 pixels)
            if not (18 <= w <= 32 and 18 <= h <= 32):
                continue
            
            # Must be nearly square
            aspect_ratio = w / h if h > 0 else 0
            if not (0.85 < aspect_ratio < 1.15):
                continue
            
            area = cv2.contourArea(contour)
            if area < 300:
                continue
            
            center_x = x + w // 2
            center_y = y + h // 2
            
            # Position filter - DIFFERENT for each captcha type
            if captcha_type == 'full_page':
                # Full page captcha - LEFT side of screen (x: 150-400, y: 200-400)
                if not (150 < center_x < 400 and 200 < center_y < 400):
                    continue
            else:  # main_page
                # Main page captcha - RIGHT-CENTER area (x: 500-900, y: 300-550)
                if not (500 < center_x < 900 and 300 < center_y < 550):
                    continue
            
            checkbox_candidates.append({
                'method': 'color',
                'x': x, 'y': y, 'w': w, 'h': h,
                'center_x': center_x,
                'center_y': center_y,
                'aspect_ratio': aspect_ratio,
                'score': 10  # Base score for color method
            })
        
        # METHOD 2: Adaptive threshold edge detection
        adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                 cv2.THRESH_BINARY, 11, 2)
        
        # Invert so checkbox border is white
        adaptive_thresh = cv2.bitwise_not(adaptive_thresh)
        
        # Find contours
        contours_adaptive, _ = cv2.findContours(adaptive_thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours_adaptive:
            x, y, w, h = cv2.boundingRect(contour)
            
            if not (18 <= w <= 32 and 18 <= h <= 32):
                continue
            
            aspect_ratio = w / h if h > 0 else 0
            if not (0.85 < aspect_ratio < 1.15):
                continue
            
            area = cv2.contourArea(contour)
            if area < 300:
                continue
            
            center_x = x + w // 2
            center_y = y + h // 2
            
            # Position filter - DIFFERENT for each captcha type
            if captcha_type == 'full_page':
                # Full page captcha - LEFT side
                if not (150 < center_x < 400 and 200 < center_y < 400):
                    continue
            else:  # main_page
                # Main page captcha - RIGHT-CENTER area
                if not (500 < center_x < 900 and 300 < center_y < 550):
                    continue
            
            checkbox_candidates.append({
                'method': 'adaptive',
                'x': x, 'y': y, 'w': w, 'h': h,
                'center_x': center_x,
                'center_y': center_y,
                'aspect_ratio': aspect_ratio,
                'score': 8
            })
        
        # METHOD 3: Multiple Canny thresholds
        # Try very low thresholds to catch subtle edges
        for low_thresh, high_thresh in [(10, 50), (20, 60), (30, 90)]:
            edges = cv2.Canny(gray, low_thresh, high_thresh)
            
            # Dilate to connect edges
            kernel = np.ones((3, 3), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=2)
            
            contours_canny, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours_canny:
                x, y, w, h = cv2.boundingRect(contour)
                
                if not (18 <= w <= 32 and 18 <= h <= 32):
                    continue
                
                aspect_ratio = w / h if h > 0 else 0
                if not (0.85 < aspect_ratio < 1.15):
                    continue
                
                area = cv2.contourArea(contour)
                if area < 300:
                    continue
                
                center_x = x + w // 2
                center_y = y + h // 2
                
                # Position filter - DIFFERENT for each captcha type
                if captcha_type == 'full_page':
                    # Full page captcha - LEFT side
                    if not (150 < center_x < 400 and 200 < center_y < 400):
                        continue
                else:  # main_page
                    # Main page captcha - RIGHT-CENTER area
                    if not (500 < center_x < 900 and 300 < center_y < 550):
                        continue
                
                checkbox_candidates.append({
                    'method': f'canny_{low_thresh}_{high_thresh}',
                    'x': x, 'y': y, 'w': w, 'h': h,
                    'center_x': center_x,
                    'center_y': center_y,
                    'aspect_ratio': aspect_ratio,
                    'score': 6
                })
        
        # Deduplicate candidates (remove those very close to each other)
        def are_close(c1, c2, threshold=15):
            return abs(c1['center_x'] - c2['center_x']) < threshold and abs(c1['center_y'] - c2['center_y']) < threshold
        
        unique_candidates = []
        for candidate in checkbox_candidates:
            is_duplicate = False
            for unique in unique_candidates:
                if are_close(candidate, unique):
                    # Keep the one with higher score
                    if candidate['score'] > unique['score']:
                        unique_candidates.remove(unique)
                        unique_candidates.append(candidate)
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_candidates.append(candidate)
        
        checkbox_candidates = unique_candidates
        
        # Score candidates based on position and characteristics
        for candidate in checkbox_candidates:
            center_x = candidate['center_x']
            center_y = candidate['center_y']
            
            # Expected position - COMPLETELY DIFFERENT for each captcha type
            if captcha_type == 'full_page':
                # Full page captcha - LEFT side (from screenshots: ~222, 288)
                expected_x = 240
                expected_y = 290
            else:  # main_page
                # Main page captcha - RIGHT-CENTER area (from screenshots: ~680, 430)
                expected_x = 680
                expected_y = 430
            
            dist_x = abs(center_x - expected_x)
            dist_y = abs(center_y - expected_y)
            
            # Closer to expected position = higher score
            if dist_x < 30 and dist_y < 30:
                candidate['score'] += 20
            elif dist_x < 50 and dist_y < 50:
                candidate['score'] += 15
            elif dist_x < 80 and dist_y < 80:
                candidate['score'] += 10
            elif dist_x < 120 and dist_y < 120:
                candidate['score'] += 5
            
            # Perfect square aspect ratio
            if 0.95 < candidate['aspect_ratio'] < 1.05:
                candidate['score'] += 3
        
        # Sort by score
        checkbox_candidates.sort(key=lambda c: c['score'], reverse=True)
        
        # Click the best candidate
        if checkbox_candidates:
            target = checkbox_candidates[0]
            click_x = target['center_x']
            click_y = target['center_y']
            
            if DEBUG:
                print(f"   ✅ Found CAPTCHA ({captcha_type}) at ({click_x}, {click_y}), Score: {target['score']}")
            
            await page.mouse.click(click_x, click_y)
            return True
        else:
            if DEBUG:
                print(f"   ❌ No CAPTCHA checkbox found ({captcha_type})")
            return False
        
    except Exception as e:
        if DEBUG:
            print(f"   ⚠️  CAPTCHA detection error ({captcha_type}): {str(e)[:100]}")
        return False


async def simple_page_load(domain, proxy=None):
    """
    Ahrefs page loading with CAPTCHA solving and metrics extraction
    """
    start_time = time.time()
    
    try:
        if DEBUG:
            print(f"[{domain}] 🔄 Starting page load...")
        
        # Get or create context
        context = await get_or_create_context(proxy)
        
        # Create page in context
        page = await create_page_in_context(context, domain)
        
        try:
            # Navigate to Ahrefs
            try_count = 3
            for attempt in range(try_count):
                try:
                    url = f"https://ahrefs.com/website-authority-checker/?input={domain}"
                    if DEBUG:
                        print(f"[{domain}] 🌐 Navigating to Ahrefs...")
                    
                    await page.goto(url, wait_until='commit', timeout=1000)
                    if DEBUG:
                        print(f"[{domain}] ✅ Page first byte received")
                    await page.wait_for_load_state('networkidle', timeout=90000)
                    
                    # Wait for page to settle
                    await asyncio.sleep(10)
                    
                    # Handle CAPTCHA #1: Full Page CAPTCHA (appears first, left side)
                    first_captcha_found = await find_and_click_captcha(page, 'full_page')
                    
                    if first_captcha_found:
                        await asyncio.sleep(10)
                        await page.wait_for_load_state('networkidle')
                    
                    # Handle CAPTCHA #2: Main Page CAPTCHA (appears on page, right-center)
                    second_captcha_found = await find_and_click_captcha(page, 'main_page')
                    
                    if second_captcha_found:
                        await page.wait_for_load_state('networkidle')
                        await asyncio.sleep(15)
                    
                    # Extract metrics
                    metrics = await extract_metrics(page)
                    
                    # Take screenshot (only if DEBUG)
                    if DEBUG:
                        try:
                            screenshot_path = f"screenshots/{domain.replace('/', '_')}.jpg"
                            await page.screenshot(
                                path=screenshot_path,
                                type='jpeg',
                                quality=85,
                                animations='disabled',
                                timeout=10000
                            )
                            print(f"[{domain}] 📸 Screenshot saved: {screenshot_path}")
                        except Exception as e:
                            print(f"[{domain}] ⚠️  Screenshot failed: {str(e)[:50]}")
                    
                    elapsed = time.time() - start_time
                    
                    # Print summary (compact format)
                    dr_str = str(metrics['_dr']) if metrics['_dr'] is not None else 'N/A'
                    bl_str = str(metrics['backlinks']) if metrics['backlinks'] is not None else 'N/A'
                    lw_str = str(metrics['linking_websites']) if metrics['linking_websites'] is not None else 'N/A'
                    
                    print(f"✅ {domain:30s} | DR: {dr_str:>4} | "
                          f"Backlinks: {bl_str:>8} | "
                          f"Linking: {lw_str:>6} | "
                          f"Time: {elapsed:.1f}s")
                    
                    result = {
                        'domain': domain,
                        'dr': metrics['_dr'],
                        'backlinks': metrics['backlinks'],
                        'linking_websites': metrics['linking_websites'],
                        'elapsed': round(elapsed, 2),
                        'captcha_1': first_captcha_found,
                        'captcha_2': second_captcha_found,
                        'success': True,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    return result
                except Exception as e:
                    if DEBUG:
                        print(f"[{domain}] ⚠️  Error on try {attempt + 1}: {str(e)[:50]}")
                    if attempt < try_count - 1:
                        await asyncio.sleep(1)
                        continue
                    raise
            
        finally:
            # Close page (keep context open - Test 4 approach)
            if DEBUG:
                print(f"[{domain}] 🧹 Closing page...")
            await page.close()
            
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)[:200]
        print(f"❌ {domain:30s} | FAILED in {elapsed:.1f}s - {error_msg[:50]}")
        
        return {
            'domain': domain,
            'error': error_msg,
            'elapsed': round(elapsed, 2),
            'success': False,
            'timestamp': datetime.now().isoformat()
        }


async def process_task(task_data):
    """Process a single task from the queue"""
    global current_processing_count
    
    domain = task_data['domain']
    proxy = task_data.get('proxy')
    
    try:
        # Execute the simple page load
        result = await simple_page_load(domain, proxy)
        
        # Store result
        if result['success']:
            completed_tasks.append(result)
        else:
            failed_tasks.append(result)
        
        return result
        
    finally:
        # Decrement processing count
        with processing_count_lock:
            current_processing_count -= 1
        
        # Start next task if available
        asyncio.create_task(start_task_from_queue())


async def start_task_from_queue():
    """Start processing the next task from queue if conditions allow"""
    global current_processing_count
    
    with processing_count_lock:
        # Check if we can start a new task
        if current_processing_count >= MAX_CONCURRENT_PROCESSING:
            return False
        
        if not task_queue:
            return False
        
        # Get next task
        task_data = task_queue.pop(0)
        current_processing_count += 1
    
    # Process task
    asyncio.create_task(process_task(task_data))
    return True


def add_task_to_queue(domain, proxy=None):
    """Add a task to the queue and try to start it"""
    task_data = {
        'domain': domain,
        'proxy': proxy,
        'added_at': datetime.now().isoformat()
    }
    
    task_queue.append(task_data)
    
    # Try to start processing
    asyncio.run_coroutine_threadsafe(start_task_from_queue(), global_loop)
    
    return {
        'message': 'Task added to queue',
        'domain': domain,
        'queue_position': len(task_queue),
        'current_processing': current_processing_count
    }


# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/load', methods=['POST'])
def load_domain():
    """Load a single domain"""
    data = request.json or {}
    domain = data.get('domain')
    
    if not domain:
        return jsonify({'error': 'domain is required'}), 400
    
    # Parse proxy if provided
    proxy = None
    if data.get('proxy'):
        proxy = parse_proxy(data['proxy'])
    
    result = add_task_to_queue(domain, proxy)
    return jsonify(result)


@app.route('/batch', methods=['POST'])
def batch_load():
    """Load multiple domains"""
    data = request.json or {}
    domains = data.get('domains', [])
    
    if not domains:
        return jsonify({'error': 'domains array is required'}), 400
    
    # Parse proxy if provided (same proxy for all domains)
    proxy = None
    if data.get('proxy'):
        proxy = parse_proxy(data['proxy'])
    
    # Add all domains to queue
    results = []
    for domain in domains:
        result = add_task_to_queue(domain, proxy)
        results.append(result)
    
    return jsonify({
        'message': f'Added {len(domains)} domains to queue',
        'domains': results,
        'queue_length': len(task_queue),
        'current_processing': current_processing_count
    })


@app.route('/queue', methods=['GET'])
def get_queue_status():
    """Get current queue status"""
    return jsonify({
        'queue_length': len(task_queue),
        'processing_count': current_processing_count,
        'max_concurrent': MAX_CONCURRENT_PROCESSING,
        'completed_count': len(completed_tasks),
        'failed_count': len(failed_tasks),
        'context_pool': get_context_pool_stats()
    })


@app.route('/results', methods=['GET'])
def get_results():
    """Get all results"""
    return jsonify({
        'completed': completed_tasks,
        'failed': failed_tasks,
        'total': len(completed_tasks) + len(failed_tasks)
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'queue_length': len(task_queue),
        'processing_count': current_processing_count
    })


# ============================================================================
# Event Loop Management
# ============================================================================

def run_event_loop(loop):
    """Run the event loop in a separate thread"""
    asyncio.set_event_loop(loop)
    loop.run_forever()


async def initialize_server():
    """Initialize browser and global resources"""
    print("🚀 Initializing browser...")
    await initialize_browser()
    print("✅ Browser initialized!")


async def cleanup_server():
    """Cleanup resources"""
    print("🔒 Closing browser...")
    await close_browser()
    print("✅ Browser closed!")


def startup():
    """Server startup"""
    global global_loop, loop_thread
    
    print("=" * 80)
    print("🚀 Starting Ahrefs Scraper with CAPTCHA Solving (run2.py)")
    print("=" * 80)
    print(f"Max concurrent processing: {MAX_CONCURRENT_PROCESSING}")
    print(f"Test approach: Queue-based concurrent page loading")
    print(f"Camoufox bug fix: Context/page creation serialized (Test 4)")
    print(f"CAPTCHA: Computer vision detection (OpenCV)")
    print("=" * 80)
    
    # Create and start event loop in separate thread
    global_loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=run_event_loop, args=(global_loop,), daemon=True)
    loop_thread.start()
    
    # Initialize browser
    asyncio.run_coroutine_threadsafe(initialize_server(), global_loop).result()
    
    print("✅ Server ready!")
    print("=" * 80)


def shutdown():
    """Server shutdown"""
    global global_loop
    
    print()
    print("=" * 80)
    print("🛑 Shutting down server...")
    print("=" * 80)
    
    if global_loop:
        # Cleanup
        asyncio.run_coroutine_threadsafe(cleanup_server(), global_loop).result()
        
        # Stop event loop
        global_loop.call_soon_threadsafe(global_loop.stop)
    
    print("✅ Shutdown complete!")


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    import os
    import signal
    import sys
    
    # Create screenshots directory
    os.makedirs('screenshots', exist_ok=True)
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print("\n⚠️  Received interrupt signal...")
        shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Startup
    startup()
    
    # Run Flask
    try:
        app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
    finally:
        shutdown()

