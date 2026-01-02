#!/usr/bin/env python3
"""
Access via Tailscale: http://100.124.226.72:8000
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

async def scrape_complete(domain):
    async with AsyncCamoufox(
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
    ) as browser:
        context = await browser.new_context()
        page = await context.new_page()
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
            await asyncio.sleep(7)

        # CAPTCHA #2: Main Page CAPTCHA (appears on page, RIGHT-CENTER area)
        # Try this regardless of whether CAPTCHA #1 was found
        # print("\n🔍 Looking for CAPTCHA #2 (MAIN PAGE CAPTCHA - RIGHT SIDE)...")
        second_captcha_found = await find_and_click_captcha('main_page', 2)

        if second_captcha_found:
            await asyncio.sleep(7)
        
        # Extract metrics
        metrics = await extract_metrics(page)
        # print(metrics)
        
        result = {
            'domain': domain,
            '_dr': metrics['_dr'],
            'backlinks': metrics['backlinks'],
            'linking_websites': metrics['linking_websites']
        }
        
        await context.close()
        await browser.close()
        
        return result

def run_async_scrape(task_id, domain):
    """Run async scrape in a new event loop"""
    try:
        jobs[task_id]['status'] = 'processing'
        jobs[task_id]['started_at'] = datetime.now().isoformat()
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(scrape_complete(domain))
        
        jobs[task_id]['status'] = 'completed'
        jobs[task_id]['completed_at'] = datetime.now().isoformat()
        results[task_id] = result
        
        print(f"✅ Task {task_id} completed: {domain}")
        
    except Exception as e:
        jobs[task_id]['status'] = 'failed'
        jobs[task_id]['error'] = str(e)
        jobs[task_id]['completed_at'] = datetime.now().isoformat()
        print(f"❌ Task {task_id} failed: {e}")

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'tailscale_ip': '100.124.226.72',
        'total_jobs': len(jobs),
        'pending': len([j for j in jobs.values() if j['status'] == 'pending']),
        'processing': len([j for j in jobs.values() if j['status'] == 'processing']),
        'completed': len([j for j in jobs.values() if j['status'] == 'completed']),
        'failed': len([j for j in jobs.values() if j['status'] == 'failed'])
    })

@app.route('/scrape', methods=['POST'])
def scrape():
    """Submit a scraping job"""
    data = request.get_json()
    
    if not data or 'domain' not in data:
        return jsonify({'error': 'Missing domain parameter'}), 400
    
    domain = data['domain']
    task_id = str(uuid.uuid4())
    
    # Store job info
    jobs[task_id] = {
        'task_id': task_id,
        'domain': domain,
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'started_at': None,
        'completed_at': None
    }
    
    # Start scraping in background thread
    thread = Thread(target=run_async_scrape, args=(task_id, domain))
    thread.daemon = True
    thread.start()
    
    print(f"📥 New job {task_id}: {domain}")
    
    return jsonify({
        'task_id': task_id,
        'domain': domain,
        'status': 'pending',
        'message': 'Job submitted successfully'
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
    """Submit multiple domains at once"""
    data = request.get_json()
    
    if not data or 'domains' not in data:
        return jsonify({'error': 'Missing domains parameter'}), 400
    
    domains = data['domains']
    
    if not isinstance(domains, list):
        return jsonify({'error': 'domains must be a list'}), 400
    
    task_ids = []
    
    for domain in domains:
        task_id = str(uuid.uuid4())
        
        jobs[task_id] = {
            'task_id': task_id,
            'domain': domain,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None
        }
        
        thread = Thread(target=run_async_scrape, args=(task_id, domain))
        thread.daemon = True
        thread.start()
        
        task_ids.append(task_id)
    
    print(f"📥 Batch job: {len(domains)} domains")
    
    return jsonify({
        'message': f'{len(domains)} jobs submitted',
        'task_ids': task_ids
    }), 202

if __name__ == '__main__':
    print("📍 Tailscale IP: 100.124.226.72")
    print("🌐 Access from K8s: http://100.124.226.72:8000")
    print("")
    
    # Run on all interfaces so Tailscale can access
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)