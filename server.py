#!/usr/bin/env python3
"""
Access via Tailscale: http://100.124.226.72:8000

Architecture (Test 4 Approach for ALL - 100% Success Rate):
- Single persistent Camoufox browser instance (initialized on startup)
- WITHOUT proxy: ONE shared context + pages only
- WITH proxy: ONE shared context per unique proxy + pages only (context pooling)
- NO semaphore (testing if deadlock occurs on Mac)
- NO new contexts per request (contexts are reused)
- Browser is reused across all requests for better performance
- Tasks are processed through a queue with 3 concurrent workers
- Browser is properly closed on server shutdown

Context Pooling Strategy:
- Non-proxy requests: All share 1 context
- Proxy requests: Each unique proxy gets 1 shared context
- All requests create pages only (NO new contexts per request)
- Example: 100 proxies = 100 shared contexts (created once, reused for all requests)

Queue System:
- All scrape requests are added to a queue
- Up to 3 tasks can process concurrently (3 workers)
- When a page loads (network idle), next task from queue starts automatically
- This balances throughput with browser stability
- Status flow: queued -> processing -> completed/failed

Why Test 4 Approach for Both?
- Test 4 achieved 100% success (30/30 tasks) with shared context + pages only
- NO first-byte timeout issues
- NO page loading issues
- NO semaphore needed (actually hurts performance)
- Simpler, faster, and more reliable
- Full proxy support with context pooling
"""

from flask import Flask, request, jsonify
import asyncio
from threading import Thread
import uuid
from datetime import datetime
from camoufox import AsyncCamoufox
import cv2
import numpy as np
from dotenv import load_dotenv
import os
from browserforge.fingerprints import Screen
import base64

load_dotenv()

app = Flask(__name__)

# In-memory storage for jobs and results
jobs = {}
results = {}

# Global browser instance (will be initialized on startup)
global_browser = None
browser_lock = asyncio.Lock()

# Test 4 approach: Shared contexts (one per unique proxy + one for non-proxy)
shared_context_no_proxy = None  # For non-proxy requests
shared_contexts_with_proxy = {}  # Dict: proxy_key -> context (for proxy requests)
context_pool_lock = asyncio.Lock()

# Global event loop for all async operations
global_loop = None
loop_thread = None

# Task queue for concurrent processing
task_queue = []
queue_lock = asyncio.Lock()

# Concurrent processing control (3 workers, Test 4 approach, NO semaphore)
MAX_CONCURRENT_PROCESSING = 3
current_processing_count = 0
processing_count_lock = asyncio.Lock()

async def initialize_browser():
    """Initialize the global browser instance"""
    global global_browser
    
    if global_browser is None:
        print("🚀 Initializing Camoufox browser instance...")
        global_browser = await AsyncCamoufox(
            headless=False,
            humanize=True,
            screen=Screen(
                min_width=1300,
                max_width=1300,
                min_height=768,
                max_height=768
            ),
            window=(1300, 768),
            i_know_what_im_doing=True,
            config={'forceScopeAccess': True},
            disable_coop=True,
        ).__aenter__()
        print("✅ Browser instance ready!")
    
    return global_browser

async def close_browser():
    """Close all shared contexts and global browser instance"""
    global global_browser, shared_context_no_proxy, shared_contexts_with_proxy
    
    # Close non-proxy shared context
    if shared_context_no_proxy is not None:
        print("🔒 Closing non-proxy shared context...")
        await shared_context_no_proxy.close()
        shared_context_no_proxy = None
        print("✅ Non-proxy context closed!")
    
    # Close all proxy shared contexts
    if shared_contexts_with_proxy:
        print(f"🔒 Closing {len(shared_contexts_with_proxy)} proxy contexts...")
        for proxy_key, context in shared_contexts_with_proxy.items():
            await context.close()
            print(f"   ✅ Closed context for proxy: {proxy_key}")
        shared_contexts_with_proxy.clear()
        print("✅ All proxy contexts closed!")
    
    # Then close browser
    if global_browser is not None:
        print("🔒 Closing browser instance...")
        await global_browser.__aexit__(None, None, None)
        global_browser = None
        print("✅ Browser closed!")

async def extract_metrics(page):
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

async def scrape_complete(domain, proxy=None, page_loaded_callback=None):
    """Scrape domain using the global browser instance
    
    Test 4 Approach for BOTH proxy and non-proxy (100% success):
    - WITHOUT proxy: ONE shared context + new page only
    - WITH proxy: ONE shared context per unique proxy + new page only
    - NO semaphore needed
    - All pages share contexts (context pooling)
    
    Args:
        domain: Domain to scrape
        proxy: Dict with keys: server, username, password (optional)
        page_loaded_callback: Optional callback to call when page is loaded
    """
    global global_browser, shared_context_no_proxy, shared_contexts_with_proxy
    
    # Ensure browser is initialized
    if global_browser is None:
        await initialize_browser()
    else:
        print(f"♻️  Reusing existing browser instance for {domain}")
    
    # Get or create shared context (Test 4 approach)
    context = None
    
    if proxy:
        # WITH PROXY: Get or create shared context for this specific proxy
        proxy_key = f"{proxy['server']}"  # Unique key per proxy
        
        async with context_pool_lock:
            if proxy_key not in shared_contexts_with_proxy:
                print(f"🆕 Creating shared context for proxy: {proxy_key}")
                shared_contexts_with_proxy[proxy_key] = await global_browser.new_context(proxy=proxy)
                print(f"✅ Proxy context created! (Total contexts: {len(shared_contexts_with_proxy) + 1})")
            
            context = shared_contexts_with_proxy[proxy_key]
        
        print(f"♻️  Reusing shared context for proxy: {proxy_key}")
    else:
        # WITHOUT PROXY: Use shared non-proxy context
        async with context_pool_lock:
            if shared_context_no_proxy is None:
                print(f"🆕 Creating shared context for non-proxy requests...")
                shared_context_no_proxy = await global_browser.new_context()
                print(f"✅ Non-proxy context created!")
            
            context = shared_context_no_proxy
        
        print(f"♻️  Reusing shared non-proxy context")
    
    # Create page in shared context (NO semaphore - Test 4 approach)
    page = await context.new_page()
    print(f"📄 New page created for {domain} (Test 4: shared context + page only)")
    
    try:
        # Decode base64 text to string
        _url = 'aHR0cHM6Ly9haHJlZnMuY29tL3dlYnNpdGUtYXV0aG9yaXR5LWNoZWNrZXI/aW5wdXQ9'
        _url = base64.b64decode(_url).decode('utf-8')

        url = f'{_url}{domain}'
        await page.goto(url, wait_until='networkidle', timeout=80000)
        print(f"🔍 Page loaded for {domain}")
        
        await asyncio.sleep(10)
        
        # Function to find and click CAPTCHA checkbox
        async def find_and_click_captcha(captcha_type, attempt_number):
            """
            captcha_type: 'full_page' or 'main_page'
            attempt_number: 1 or 2
            """
            # Screenshot
            screenshot_bytes = await page.screenshot()
            img_array = np.frombuffer(screenshot_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            checkbox_candidates = []
            
            # METHOD 1: Color-based detection (look for white/light squares)
            # print("🔍 Method 1: Color-based detection...")
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
            
            # print(f"  Found {len(checkbox_candidates)} candidates from color detection")
            
            # METHOD 2: Adaptive threshold edge detection
            # print("🔍 Method 2: Adaptive threshold...")
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
            
            # print(f"  Found {len([c for c in checkbox_candidates if c['method']=='adaptive'])} candidates from adaptive threshold")
            
            # METHOD 3: Multiple Canny thresholds
            # print("🔍 Method 3: Multi-threshold Canny...")
            
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
            
            # print(f"  Total candidates now: {len(checkbox_candidates)}")
            
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
            # print(f"  After deduplication: {len(checkbox_candidates)} candidates")
            
            # Score candidates based on position and characteristics
            for candidate in checkbox_candidates:
                center_x = candidate['center_x']
                center_y = candidate['center_y']
                
                # Expected position - COMPLETELY DIFFERENT for each captcha type
                if captcha_type == 'full_page':
                    # Full page captcha - LEFT side (from your screenshot: ~222, 288)
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
            
            # Draw all candidates
            candidates_img = img.copy()
            for idx, candidate in enumerate(checkbox_candidates[:10]):
                color = (0, 255, 0) if idx == 0 else (255, 165, 0) if idx < 3 else (0, 165, 255)
                thickness = 3 if idx == 0 else 2
                cv2.rectangle(candidates_img, (candidate['x'], candidate['y']), 
                            (candidate['x']+candidate['w'], candidate['y']+candidate['h']), color, thickness)
                cv2.putText(candidates_img, f"#{idx+1}:S{candidate['score']}", 
                          (candidate['x'], candidate['y']-5), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            
            # Print top candidates
            # print(f"\n📊 Top candidates for {captcha_type.upper().replace('_', ' ')} CAPTCHA:")
            # for idx, candidate in enumerate(checkbox_candidates[:5]):
            #     print(f"  #{idx+1}: Method={candidate['method']}, "
            #           f"Pos({candidate['center_x']}, {candidate['center_y']}), "
            #           f"Size={candidate['w']}x{candidate['h']}, Score={candidate['score']}")
            
            # Click the best candidate
            if checkbox_candidates:
                target = checkbox_candidates[0]
                click_x = target['center_x']
                click_y = target['center_y']
                
                # Draw final clicked position
                final_img = img.copy()
                cv2.rectangle(final_img, (target['x'], target['y']), 
                            (target['x']+target['w'], target['y']+target['h']), (0, 0, 255), 3)
                cv2.circle(final_img, (click_x, click_y), 5, (0, 0, 255), -1)
                cv2.putText(final_img, f"CLICKED: ({click_x}, {click_y})", 
                          (click_x + 10, click_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                await page.mouse.click(click_x, click_y)
                return True
            else:
                # print(f"\n❌ No checkbox found for {captcha_type.upper().replace('_', ' ')} CAPTCHA")
                return False
        
        # CAPTCHA #1: Full Page CAPTCHA (appears first, full screen, LEFT side)
        # print("\n🔍 Looking for CAPTCHA #1 (FULL PAGE CAPTCHA - LEFT SIDE)...")
        first_captcha_found = await find_and_click_captcha('full_page', 1)

        if first_captcha_found:
            await asyncio.sleep(10)
            await page.wait_for_load_state('networkidle')
        
        # Trigger callback to start next domain (after first CAPTCHA handled)
        print(f"✨ First CAPTCHA handled for {domain}, starting next task...")
        if page_loaded_callback:
            await page_loaded_callback()

        # CAPTCHA #2: Main Page CAPTCHA (appears on page, RIGHT-CENTER area)
        # Try this regardless of whether CAPTCHA #1 was found
        # print("\n🔍 Looking for CAPTCHA #2 (MAIN PAGE CAPTCHA - RIGHT SIDE)...")
        second_captcha_found = await find_and_click_captcha('main_page', 2)

        if second_captcha_found:
            await asyncio.sleep(15)
            await page.wait_for_load_state('networkidle')
        
        # Extract metrics
        metrics = await extract_metrics(page)
        # print(metrics)
        
        result = {
            'domain': domain,
            '_dr': metrics['_dr'],
            'backlinks': metrics['backlinks'],
            'linking_websites': metrics['linking_websites']
        }
        
        return result
        
    finally:
        # Only close page, keep context open (Test 4 approach for all)
        print(f"🧹 Cleaning up page for {domain} (keeping shared context open)")
        await page.close()

async def process_next_task():
    """Process one task from the queue (up to MAX_CONCURRENT_PROCESSING at a time)"""
    global task_queue, current_processing_count
    
    # Get next task
    async with queue_lock:
        if len(task_queue) == 0:
            print("📭 Queue empty - no more tasks")
            return
        
        task = task_queue.pop(0)
        task_id = task['task_id']
        domain = task['domain']
        proxy = task.get('proxy')
    
    # Increment processing count
    async with processing_count_lock:
        current_processing_count += 1
        processing = current_processing_count
    
    # Process this task
    print(f"🔄 Processing from queue: {domain} (Processing: {processing}/{MAX_CONCURRENT_PROCESSING}, Queue: {len(task_queue)})")
    
    # Callback to trigger next task when page loads
    async def on_page_loaded():
        print(f"✨ Page loaded for {domain}, checking for next task...")
        # Try to start next task if capacity available
        await start_next_if_possible()
    
    try:
        jobs[task_id]['status'] = 'processing'
        jobs[task_id]['started_at'] = datetime.now().isoformat()
        
        # Pass callback - next task starts when page loads, not when scraping completes
        result = await scrape_complete(domain, proxy, page_loaded_callback=on_page_loaded)
        
        jobs[task_id]['status'] = 'completed'
        jobs[task_id]['completed_at'] = datetime.now().isoformat()
        results[task_id] = result
        
        print(f"✅ Task {task_id} completed: {domain}")
        
    except Exception as e:
        jobs[task_id]['status'] = 'failed'
        jobs[task_id]['error'] = str(e)
        jobs[task_id]['completed_at'] = datetime.now().isoformat()
        print(f"❌ Task {task_id} failed: {e}")
    
    finally:
        # Decrement processing count
        async with processing_count_lock:
            current_processing_count -= 1
            processing = current_processing_count
        
        print(f"🏁 Task finished: {domain} (Processing now: {processing}/{MAX_CONCURRENT_PROCESSING})")
        
        # Try to start next task
        await start_next_if_possible()

async def start_next_if_possible():
    """Start next task from queue if under the concurrent limit"""
    global current_processing_count
    
    async with processing_count_lock:
        can_start = current_processing_count < MAX_CONCURRENT_PROCESSING
        processing = current_processing_count
    
    if can_start and len(task_queue) > 0:
        print(f"🚀 Starting next task (Processing: {processing}/{MAX_CONCURRENT_PROCESSING})")
        asyncio.create_task(process_next_task())
    elif processing >= MAX_CONCURRENT_PROCESSING:
        print(f"⏸️  At capacity ({MAX_CONCURRENT_PROCESSING}/{MAX_CONCURRENT_PROCESSING}), waiting for slot...")
    else:
        print(f"📭 No more tasks in queue")

async def add_task_to_queue(task_id, domain, proxy=None):
    """Add a task to the queue and start processing if capacity available"""
    global task_queue, current_processing_count
    
    # Add task to queue
    async with queue_lock:
        task_queue.append({
            'task_id': task_id,
            'domain': domain,
            'proxy': proxy
        })
        queue_size = len(task_queue)
    
    async with processing_count_lock:
        processing = current_processing_count
    
    print(f"📥 Added to queue: {domain} (Queue: {queue_size}, Processing: {processing}/{MAX_CONCURRENT_PROCESSING})")
    
    # Try to start this task if we have capacity
    await start_next_if_possible()

def run_async_scrape(task_id, domain, proxy=None):
    """Submit scrape task to the queue via global event loop"""
    global global_loop
    
    if global_loop is None:
        print(f"❌ Global event loop not initialized!")
        jobs[task_id]['status'] = 'failed'
        jobs[task_id]['error'] = 'Event loop not initialized'
        return
    
    # Add task to queue (will be processed sequentially)
    asyncio.run_coroutine_threadsafe(add_task_to_queue(task_id, domain, proxy), global_loop)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'tailscale_ip': '100.124.226.72',
        'total_jobs': len(jobs),
        'queued': len([j for j in jobs.values() if j['status'] == 'queued']),
        'processing': len([j for j in jobs.values() if j['status'] == 'processing']),
        'completed': len([j for j in jobs.values() if j['status'] == 'completed']),
        'failed': len([j for j in jobs.values() if j['status'] == 'failed']),
        'queue_size': len(task_queue),
        'max_concurrent': MAX_CONCURRENT_PROCESSING,
        'current_processing': current_processing_count,
        'context_pool': {
            'no_proxy_context': 'created' if shared_context_no_proxy else 'not created',
            'proxy_contexts': len(shared_contexts_with_proxy),
            'total_contexts': (1 if shared_context_no_proxy else 0) + len(shared_contexts_with_proxy)
        }
    })

@app.route('/queue', methods=['GET'])
def queue_status():
    """Get current queue status"""
    queue_items = []
    for task in task_queue:
        queue_items.append({
            'task_id': task['task_id'],
            'domain': task['domain'],
            'has_proxy': task.get('proxy') is not None
        })
    
    return jsonify({
        'queue_size': len(task_queue),
        'processing_count': len([j for j in jobs.values() if j['status'] == 'processing']),
        'queue': queue_items
    })

@app.route('/scrape', methods=['POST'])
def scrape():
    """Submit a scraping job
    
    Request body:
        domain (required): Domain to scrape
        proxy_ip (optional): Proxy IP address
        proxy_port (optional): Proxy port
        proxy_user (optional): Proxy username
        proxy_pass (optional): Proxy password
    """
    data = request.get_json()
    
    if not data or 'domain' not in data:
        return jsonify({'error': 'Missing domain parameter'}), 400
    
    domain = data['domain']
    task_id = str(uuid.uuid4())
    
    # Build proxy dict if proxy parameters provided
    proxy = None
    if 'proxy_ip' in data and 'proxy_port' in data:
        proxy_server = f"http://{data['proxy_ip']}:{data['proxy_port']}"
        proxy = {
            'server': proxy_server
        }
        
        # Add authentication if provided
        if 'proxy_user' in data and 'proxy_pass' in data:
            proxy['username'] = data['proxy_user']
            proxy['password'] = data['proxy_pass']
    
    # Store job info
    jobs[task_id] = {
        'task_id': task_id,
        'domain': domain,
        'status': 'queued',
        'created_at': datetime.now().isoformat(),
        'started_at': None,
        'completed_at': None,
        'proxy': proxy_server if proxy else None
    }
    
    # Add to queue (will be processed sequentially)
    thread = Thread(target=run_async_scrape, args=(task_id, domain, proxy))
    thread.daemon = True
    thread.start()
    
    print(f"📥 New job {task_id}: {domain}" + (f" [proxy: {proxy_server}]" if proxy else ""))
    
    return jsonify({
        'task_id': task_id,
        'domain': domain,
        'status': 'queued',
        'proxy': proxy_server if proxy else None,
        'message': 'Job queued successfully'
    }), 202

@app.route('/result/<task_id>', methods=['GET'])
def get_result(task_id):
    """Get result of a scraping job"""
    if task_id not in jobs:
        return jsonify({'error': 'Task not found'}), 404
    
    job = jobs[task_id]
    
    response = {
        'task_id': task_id,
        'domain': job['domain'],
        'status': job['status'],
        'created_at': job['created_at'],
        'started_at': job.get('started_at'),
        'completed_at': job.get('completed_at')
    }
    
    if job['status'] == 'completed':
        response['result'] = results.get(task_id)
    elif job['status'] == 'failed':
        response['error'] = job.get('error')
    
    return jsonify(response)

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all jobs"""
    status_filter = request.args.get('status')
    
    job_list = list(jobs.values())
    
    if status_filter:
        job_list = [j for j in job_list if j['status'] == status_filter]
    
    return jsonify({
        'total': len(job_list),
        'jobs': job_list
    })

@app.route('/batch', methods=['POST'])
def batch_scrape():
    """Submit multiple domains at once
    
    Request body:
        domains (required): List of domains (strings) or list of objects with:
            - domain (required)
            - proxy_ip, proxy_port, proxy_user, proxy_pass (optional)
    """
    data = request.get_json()
    
    if not data or 'domains' not in data:
        return jsonify({'error': 'Missing domains parameter'}), 400
    
    domains = data['domains']
    
    if not isinstance(domains, list):
        return jsonify({'error': 'domains must be a list'}), 400
    
    task_ids = []
    
    for item in domains:
        # Support both string domains and object with domain + proxy
        if isinstance(item, str):
            domain = item
            proxy = None
        elif isinstance(item, dict):
            domain = item.get('domain')
            if not domain:
                continue  # Skip items without domain
            
            # Build proxy dict if proxy parameters provided
            proxy = None
            if 'proxy_ip' in item and 'proxy_port' in item:
                proxy_server = f"http://{item['proxy_ip']}:{item['proxy_port']}"
                proxy = {
                    'server': proxy_server
                }
                
                # Add authentication if provided
                if 'proxy_user' in item and 'proxy_pass' in item:
                    proxy['username'] = item['proxy_user']
                    proxy['password'] = item['proxy_pass']
        else:
            continue  # Skip invalid items
        
        task_id = str(uuid.uuid4())
        
        jobs[task_id] = {
            'task_id': task_id,
            'domain': domain,
            'status': 'queued',
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
            'proxy': proxy.get('server') if proxy else None
        }
        
        thread = Thread(target=run_async_scrape, args=(task_id, domain, proxy))
        thread.daemon = True
        thread.start()
        
        task_ids.append(task_id)
    
    print(f"📥 Batch job: {len(task_ids)} domains queued")
    
    return jsonify({
        'message': f'{len(task_ids)} jobs queued (will be processed sequentially)',
        'task_ids': task_ids
    }), 202

def run_event_loop(loop):
    """Run event loop in background thread"""
    asyncio.set_event_loop(loop)
    loop.run_forever()

def startup():
    """Initialize browser and event loop on startup"""
    global global_loop, loop_thread
    
    print("🔧 Starting global event loop in background thread...")
    
    # Create event loop and run it in background thread
    global_loop = asyncio.new_event_loop()
    loop_thread = Thread(target=run_event_loop, args=(global_loop,), daemon=True)
    loop_thread.start()
    
    print("✅ Event loop started!")
    
    # Initialize browser in that loop
    future = asyncio.run_coroutine_threadsafe(initialize_browser(), global_loop)
    future.result(timeout=30)  # Wait for browser to initialize
    
    print("✅ Startup complete!")

if __name__ == '__main__':
    print("📍 Tailscale IP: 100.124.226.72")
    print("🌐 Access from K8s: http://100.124.226.72:8000")
    print("")
    
    # Initialize browser before starting server
    startup()
    
    try:
        # Run on all interfaces so Tailscale can access
        app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
    finally:
        # Cleanup on shutdown
        print("\n🛑 Shutting down...")
        if global_loop and global_loop.is_running():
            # Close browser in the global loop
            future = asyncio.run_coroutine_threadsafe(close_browser(), global_loop)
            future.result(timeout=10)
            
            # Stop the event loop
            global_loop.call_soon_threadsafe(global_loop.stop)
            loop_thread.join(timeout=5)
            print("✅ Cleanup complete!")