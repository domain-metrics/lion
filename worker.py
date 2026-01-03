#!/usr/bin/env python3
"""
Worker - Processes tasks from queue
Separate process that handles browser automation
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
import sys

# Import helpers
from camoufox_helper import initialize_browser, close_browser, get_or_create_context, create_page_in_context
import cv2
import numpy as np

# Configuration
MAX_CONCURRENT_PROCESSING = 1
DEBUG = False
MAX_TIMEOUT_ERRORS = 5
QUEUE_FILE = "task_queue.json"
RESULTS_FILE = "results.json"
STATUS_FILE = "worker_status.json"
POLL_INTERVAL = 2  # seconds

# Error tracking
timeout_error_count = 0

def load_json_file(filename, default=None):
    """Load JSON file safely"""
    try:
        if Path(filename).exists():
            with open(filename, 'r') as f:
                return json.load(f)
    except:
        pass
    return default if default is not None else []

def save_json_file(filename, data):
    """Save JSON file safely with file locking"""
    temp_file = f"{filename}.tmp"
    with open(temp_file, 'w') as f:
        json.dump(data, f, indent=2)
    Path(temp_file).replace(filename)

def update_worker_status(status_info):
    """Update worker status file"""
    save_json_file(STATUS_FILE, {
        **status_info,
        'last_heartbeat': datetime.now().isoformat()
    })

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
    """Find and click CAPTCHA checkbox using computer vision"""
    try:
        screenshot_bytes = await page.screenshot()
        img_array = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        checkbox_candidates = []
        
        # METHOD 1: Color-based detection
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)
        contours_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours_white:
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
            
            if captcha_type == 'full_page':
                if not (150 < center_x < 400 and 200 < center_y < 400):
                    continue
            else:
                if not (500 < center_x < 900 and 300 < center_y < 550):
                    continue
            
            checkbox_candidates.append({
                'method': 'color',
                'x': x, 'y': y, 'w': w, 'h': h,
                'center_x': center_x,
                'center_y': center_y,
                'aspect_ratio': aspect_ratio,
                'score': 10
            })
        
        # METHOD 2: Adaptive threshold
        adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        adaptive_thresh = cv2.bitwise_not(adaptive_thresh)
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
            
            if captcha_type == 'full_page':
                if not (150 < center_x < 400 and 200 < center_y < 400):
                    continue
            else:
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
        for low_thresh, high_thresh in [(10, 50), (20, 60), (30, 90)]:
            edges = cv2.Canny(gray, low_thresh, high_thresh)
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
                
                if captcha_type == 'full_page':
                    if not (150 < center_x < 400 and 200 < center_y < 400):
                        continue
                else:
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
        
        # Deduplicate
        def are_close(c1, c2, threshold=15):
            return abs(c1['center_x'] - c2['center_x']) < threshold and abs(c1['center_y'] - c2['center_y']) < threshold
        
        unique_candidates = []
        for candidate in checkbox_candidates:
            is_duplicate = False
            for unique in unique_candidates:
                if are_close(candidate, unique):
                    if candidate['score'] > unique['score']:
                        unique_candidates.remove(unique)
                        unique_candidates.append(candidate)
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_candidates.append(candidate)
        
        checkbox_candidates = unique_candidates
        
        # Score candidates
        for candidate in checkbox_candidates:
            center_x = candidate['center_x']
            center_y = candidate['center_y']
            
            if captcha_type == 'full_page':
                expected_x = 240
                expected_y = 290
            else:
                expected_x = 680
                expected_y = 430
            
            dist_x = abs(center_x - expected_x)
            dist_y = abs(center_y - expected_y)
            
            if dist_x < 30 and dist_y < 30:
                candidate['score'] += 20
            elif dist_x < 50 and dist_y < 50:
                candidate['score'] += 15
            elif dist_x < 80 and dist_y < 80:
                candidate['score'] += 10
            elif dist_x < 120 and dist_y < 120:
                candidate['score'] += 5
            
            if 0.95 < candidate['aspect_ratio'] < 1.05:
                candidate['score'] += 3
        
        checkbox_candidates.sort(key=lambda c: c['score'], reverse=True)
        
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

async def process_domain(domain, proxy=None):
    """Process a single domain"""
    global timeout_error_count
    start_time = time.time()
    
    try:
        if DEBUG:
            print(f"[{domain}] 🔄 Starting page load...")
        
        context = await get_or_create_context(proxy)
        page = await create_page_in_context(context, domain)
        
        try:
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
                    
                    # Success - decrement timeout counter
                    if timeout_error_count > 0:
                        timeout_error_count = max(0, timeout_error_count - 1)
                    
                    await asyncio.sleep(10)
                    
                    # Handle CAPTCHAs
                    first_captcha_found = await find_and_click_captcha(page, 'full_page')
                    if first_captcha_found:
                        await asyncio.sleep(10)
                        await page.wait_for_load_state('networkidle')
                    
                    second_captcha_found = await find_and_click_captcha(page, 'main_page')
                    if second_captcha_found:
                        await page.wait_for_load_state('networkidle')
                        await asyncio.sleep(15)
                    
                    # Extract metrics
                    metrics = await extract_metrics(page)
                    
                    elapsed = time.time() - start_time
                    
                    # Print summary
                    dr_str = str(metrics['_dr']) if metrics['_dr'] is not None else 'N/A'
                    bl_str = str(metrics['backlinks']) if metrics['backlinks'] is not None else 'N/A'
                    lw_str = str(metrics['linking_websites']) if metrics['linking_websites'] is not None else 'N/A'
                    
                    print(f"✅ {domain:30s} | DR: {dr_str:>4} | Backlinks: {bl_str:>8} | Linking: {lw_str:>6} | Time: {elapsed:.1f}s")
                    
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
                    error_str = str(e)
                    is_timeout = 'Timeout' in error_str or 'timeout' in error_str
                    
                    if is_timeout:
                        timeout_error_count += 1
                        current_count = timeout_error_count
                        
                        if current_count >= MAX_TIMEOUT_ERRORS:
                            print(f"\n⚠️  Timeout error #{current_count} detected - restarting browser after current tasks...")
                            return {'domain': domain, 'error': 'Browser restart triggered', 'success': False, 'restart_needed': True}
                    
                    if DEBUG:
                        print(f"[{domain}] ⚠️  Error on try {attempt + 1}: {error_str[:50]}")
                    
                    if attempt < try_count - 1:
                        await asyncio.sleep(1)
                        continue
                    raise
            
        finally:
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

async def process_tasks():
    """Main worker loop"""
    global timeout_error_count
    
    print("🚀 Initializing browser...")
    await initialize_browser()
    print("✅ Browser ready!")
    
    currently_processing = []
    restart_needed = False
    
    while True:
        try:
            # Update worker status
            update_worker_status({
                'status': 'running',
                'processing_count': len(currently_processing),
                'timeout_errors': timeout_error_count
            })
            
            # Check if restart needed
            if restart_needed and len(currently_processing) == 0:
                print("\n" + "=" * 80)
                print("⚠️  RESTARTING BROWSER DUE TO TIMEOUT ERRORS")
                print("=" * 80)
                await close_browser()
                print("✅ Old browser closed")
                await asyncio.sleep(3)
                await initialize_browser()
                print("✅ New browser initialized")
                timeout_error_count = 0
                restart_needed = False
                print("=" * 80)
                print("✅ BROWSER RESTART COMPLETE")
                print("=" * 80 + "\n")
            
            # Load queue
            queue = load_json_file(QUEUE_FILE, [])
            
            # Get tasks to process
            pending_tasks = [t for t in queue if t.get('status') == 'queued']
            
            # Start new tasks if we have capacity
            while len(currently_processing) < MAX_CONCURRENT_PROCESSING and pending_tasks:
                task = pending_tasks.pop(0)
                task['status'] = 'processing'
                
                # Update queue
                save_json_file(QUEUE_FILE, queue)
                
                # Start processing
                async def process_and_save(task_data):
                    nonlocal restart_needed
                    domain = task_data['domain']
                    proxy = task_data.get('proxy')
                    
                    result = await process_domain(domain, proxy)
                    
                    # Check if restart needed
                    if result.get('restart_needed'):
                        restart_needed = True
                    
                    # Save result
                    results = load_json_file(RESULTS_FILE, {'completed': [], 'failed': []})
                    if result['success']:
                        results['completed'].append(result)
                    else:
                        results['failed'].append(result)
                    save_json_file(RESULTS_FILE, results)
                    
                    # Remove from queue
                    queue = load_json_file(QUEUE_FILE, [])
                    queue = [t for t in queue if t.get('domain') != domain]
                    save_json_file(QUEUE_FILE, queue)
                    
                    # Remove from currently_processing
                    currently_processing.remove(task_data)
                
                currently_processing.append(task)
                asyncio.create_task(process_and_save(task))
            
            # Wait before next poll
            await asyncio.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n⚠️  Stopping worker...")
            break
        except Exception as e:
            print(f"❌ Worker error: {str(e)}")
            await asyncio.sleep(5)
    
    print("🔒 Closing browser...")
    await close_browser()
    print("✅ Worker stopped!")

if __name__ == '__main__':
    print("=" * 80)
    print("🚀 Starting Worker (Task Processor)")
    print("=" * 80)
    print(f"Max concurrent: {MAX_CONCURRENT_PROCESSING}")
    print(f"Queue file: {QUEUE_FILE}")
    print(f"Results file: {RESULTS_FILE}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print("=" * 80)
    
    try:
        asyncio.run(process_tasks())
    except KeyboardInterrupt:
        print("\n✅ Worker stopped by user")

