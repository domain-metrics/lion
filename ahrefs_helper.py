#!/usr/bin/env python3
"""
Ahrefs Scraping Helper

Handles:
- Ahrefs page navigation
- CAPTCHA detection and clicking
- Metrics extraction (DR, backlinks, linking websites)
"""

import asyncio
import base64
import cv2
import numpy as np
from camoufox_helper import get_or_create_context, create_page_in_context

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
    
    Args:
        page: Playwright page object
        captcha_type: 'full_page' or 'main_page'
    
    Returns:
        bool: True if checkbox found and clicked, False otherwise
    """
    # Take screenshot with animations disabled (skip font waiting)
    screenshot_bytes = await page.screenshot(
        type='jpeg', 
        quality=85, 
        animations='disabled',
        timeout=30000
    )
    img_array = np.frombuffer(screenshot_bytes, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    checkbox_candidates = []
    
    # METHOD 1: Color-based detection (look for white/light squares)
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
        
        # Position filter - DIFFERENT for each captcha type
        if captcha_type == 'full_page':
            if not (150 < center_x < 400 and 200 < center_y < 400):
                continue
        else:  # main_page
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
    
    # METHOD 2: Adaptive threshold edge detection
    adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                             cv2.THRESH_BINARY, 11, 2)
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
        
        # Position filter
        if captcha_type == 'full_page':
            if not (150 < center_x < 400 and 200 < center_y < 400):
                continue
        else:  # main_page
            if not (500 < center_x < 900 and 300 < center_y < 550):
                continue
        
        checkbox_candidates.append({
            'method': 'adaptive',
            'x': x, 'y': y, 'w': w, 'h': h,
            'center_x': center_x,
            'center_y': center_y,
            'aspect_ratio': aspect_ratio,
            'score': 5
        })
    
    # Deduplicate and find best candidate
    unique_candidates = []
    for candidate in checkbox_candidates:
        is_duplicate = False
        for unique in unique_candidates:
            if abs(candidate['center_x'] - unique['center_x']) < 5 and \
               abs(candidate['center_y'] - unique['center_y']) < 5:
                if candidate['score'] > unique['score']:
                    unique_candidates.remove(unique)
                    unique_candidates.append(candidate)
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_candidates.append(candidate)
    
    # Click the best candidate
    if unique_candidates:
        best = max(unique_candidates, key=lambda c: c['score'])
        click_x = best['center_x']
        click_y = best['center_y']
        
        await page.mouse.click(click_x, click_y)
        return True
    
    return False


async def scrape_ahrefs_domain(domain, proxy=None, page_loaded_callback=None):
    """
    Scrape a domain from Ahrefs
    
    Args:
        domain: Domain to scrape
        proxy: Dict with keys: server, username, password (optional)
        page_loaded_callback: Optional callback to call when page is loaded
    
    Returns:
        dict: Scraped metrics
    """
    # Get or create shared context (Test 4 approach)
    context = await get_or_create_context(proxy)
    
    # Create page in shared context (NO semaphore - Test 4 approach)
    page = await create_page_in_context(context, domain)
    
    try:
        # Build Ahrefs URL
        _url = 'aHR0cHM6Ly9haHJlZnMuY29tL3dlYnNpdGUtYXV0aG9yaXR5LWNoZWNrZXI/aW5wdXQ9'
        _url = base64.b64decode(_url).decode('utf-8')
        url = f'{_url}{domain}'
        
        # Navigate to page (Test 4: NO semaphore for navigation, only for context/page creation)
        print(f"🔄 Navigating to {domain}...")
        await page.goto(url, wait_until='networkidle', timeout=30000)  # 30s timeout for faster failure detection
        print(f"🔍 Page loaded for {domain}")
        
        await asyncio.sleep(10)
        
        # Handle CAPTCHA #1: Full Page CAPTCHA (appears first, left side)
        first_captcha_found = await find_and_click_captcha(page, 'full_page')
        
        if first_captcha_found:
            await asyncio.sleep(10)
            await page.wait_for_load_state('networkidle')
        
        # Trigger callback to start next domain
        print(f"✨ First CAPTCHA handled for {domain}, starting next task...")
        if page_loaded_callback:
            await page_loaded_callback()
        
        # Handle CAPTCHA #2: Main Page CAPTCHA (appears on page, right-center)
        second_captcha_found = await find_and_click_captcha(page, 'main_page')
        
        if second_captcha_found:
            await asyncio.sleep(15)
            await page.wait_for_load_state('networkidle')
        
        # Extract metrics
        metrics = await extract_metrics(page)
        
        result = {
            'domain': domain,
            '_dr': metrics['_dr'],
            'backlinks': metrics['backlinks'],
            'linking_websites': metrics['linking_websites']
        }
        
        return result
        
    finally:
        # Only close page, keep context open (Test 4 approach)
        print(f"🧹 Cleaning up page for {domain} (keeping shared context open)")
        await page.close()

