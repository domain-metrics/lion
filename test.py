#!/usr/bin/env python3
"""
Parallel domain scraper - submits jobs to Mac server via Tailscale
"""

import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict
import json

MAC_SCRAPER_URL = "http://100.73.90.66:8000"
# MAC_SCRAPER_URL = "http://127.0.0.1:8000"
MAX_RETRIES = 600
RETRY_DELAY = 10  # seconds
MAX_THREADS = 1

def submit_job(domain: str) -> Optional[str]:
    """Submit a scraping job and return task_id"""
    try:
        response = requests.post(
            f"{MAC_SCRAPER_URL}/scrape",
            json={'domain': domain},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        task_id = data.get('task_id')
        print(f"✅ Submitted: {domain} -> {task_id}")
        return task_id
        
    except Exception as e:
        print(f"❌ Failed to submit {domain}: {e}")
        return None

def get_result(task_id: str, domain: str) -> Optional[Dict]:
    """Poll for result up to MAX_RETRIES times"""
    # print(f"⏳ Waiting for result: {domain} ({task_id})")
    
    try:
        response = requests.get(
            f"{MAC_SCRAPER_URL}/result/{task_id}",
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        status = result.get('status')
        
        if status == 'completed':
            # print(f"✅ Completed: {domain}")
            return result
        else:
            return None
    except Exception as e:
        print(f"⚠️  Error checking {domain}: {e}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    
    print(f"⏱️  Timeout: {domain} (exceeded {MAX_RETRIES} retries)")
    return None

def process_domain(domain: str) -> Dict:
    """Process a single domain: submit job and wait for result"""
    domain = domain.strip()
    
    if not domain:
        return None
    
    # print(f"🚀 Processing: {domain}")
    
    # Submit job
    task_id = submit_job(domain)
    if not task_id:
        return {
            'domain': domain,
            'status': 'submission_failed',
            'error': 'Failed to submit job'
        }
    
    # Wait for result
    for _ in range(MAX_RETRIES):
        result = get_result(task_id, domain)
        if result:
            return result
        time.sleep(RETRY_DELAY)
    return {
        'domain': domain,
        'status': 'timeout',
        'error': f'No result after {MAX_RETRIES * RETRY_DELAY} seconds'
    }

def main():
    # Read domains from file
    try:
        with open('domains_100.txt', 'r') as f:
            domains = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ Error: domain_list.txt not found!")
        return
    
    if not domains:
        print("❌ Error: domain_list.txt is empty!")
        return
    if not domains:
        print("❌ Error: domain_list.txt is empty!")
        return
    
    print(f"📋 Loaded {len(domains)} domains")
    print(f"🔧 Using {MAX_THREADS} parallel threads")
    print(f"⏱️  Max wait per domain: {MAX_RETRIES * RETRY_DELAY} seconds ({MAX_RETRIES} retries × {RETRY_DELAY}s)")
    print(f"🌐 Mac server: {MAC_SCRAPER_URL}")
    print("-" * 60)
    
    results = []
    
    # Process domains in parallel
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # Submit all tasks
        future_to_domain = {
            executor.submit(process_domain, domain): domain 
            for domain in domains
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_domain):
            domain = future_to_domain[future]
            try:
                result = future.result()
                if result:
                    print(result)
                    results.append(result)
            except Exception as e:
                print(f"❌ Exception for {domain}: {e}")
                results.append({
                    'domain': domain,
                    'status': 'exception',
                    'error': str(e)
                })
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    # Count statuses
    completed = len([r for r in results if r.get('status') == 'completed'])
    failed = len([r for r in results if r.get('status') == 'failed'])
    timeout = len([r for r in results if r.get('status') == 'timeout'])
    submission_failed = len([r for r in results if r.get('status') == 'submission_failed'])
    
    print(f"Total domains: {len(domains)}")
    print(f"✅ Completed: {completed}")
    print(f"❌ Failed: {failed}")
    print(f"⏱️  Timeout: {timeout}")
    print(f"🚫 Submission failed: {submission_failed}")
    
    # Save results to file
    output_file = f"scraping_results_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Show sample results
    print("\n📄 Sample Results:")
    for result in results[:5]:
        if result.get('status') == 'completed':
            print(f"\n{result.get('domain')}:")
            print(f"  Domain Rating: {result.get('result', {}).get('domain_rating')}")
            print(f"  Backlinks: {result.get('result', {}).get('backlinks')}")
            print(f"  Linking Websites: {result.get('result', {}).get('linking_websites')}")

if __name__ == '__main__':
    start_time = time.time()
    main()
    end_time = time.time()
    print(f"Time taken: {end_time - start_time} seconds")