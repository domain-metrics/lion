#!/usr/bin/env python3
"""
Test script to demonstrate the queue system WITH PROXIES
Submits domains with each getting a unique proxy from Webshare list
"""

import requests
import time
import json

SERVER_URL = "http://127.0.0.1:8000"
PROXY_FILE = "Webshare 100 proxies.txt"

def load_proxies():
    """Load proxies from file"""
    proxies = []
    
    try:
        with open(PROXY_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Format: ip:port:user:pass
                parts = line.split(':')
                if len(parts) >= 4:
                    proxies.append({
                        'proxy_ip': parts[0],
                        'proxy_port': parts[1],
                        'proxy_user': parts[2],
                        'proxy_pass': parts[3]
                    })
        
        print(f"✅ Loaded {len(proxies)} proxies from {PROXY_FILE}\n")
        return proxies
    
    except FileNotFoundError:
        print(f"❌ Proxy file not found: {PROXY_FILE}")
        return []

def submit_batch_with_proxies():
    """Submit a batch with proxies and monitor the queue"""
    
    # Load proxies
    proxies = load_proxies()
    
    if not proxies:
        print("❌ No proxies available, cannot continue")
        return []
    
    # List of domains to scrape
    domains = [
        'techcrunch.com',
        'example.com', 
        'github.com',
        'stackoverflow.com',
        'reddit.com',
        'elmleynaturereserve.co.uk',
        'aooke-anime.com',
        'freetronics.com.au',
        'roell.net',
        'tongitsfun.xyz',
        'autoeurope.eu',
        'thecarbonunderground.org',
        'speedgoat.com',
        'hotelunique.com',
        'shareindia.com',
        'techcrunch.com',
        'example.com', 
        'github.com',
        'stackoverflow.com',
        'reddit.com',
        'elmleynaturereserve.co.uk',
        'aooke-anime.com',
        'freetronics.com.au',
        'roell.net',
        'tongitsfun.xyz',
        'autoeurope.eu',
        'thecarbonunderground.org',
        'speedgoat.com',
        'hotelunique.com',
        'shareindia.com',
        'techcrunch.com',
        'example.com', 
        'github.com',
        'stackoverflow.com',
        'reddit.com',
        'elmleynaturereserve.co.uk',
        'aooke-anime.com',
        'freetronics.com.au',
        'roell.net',
        'tongitsfun.xyz',
        'autoeurope.eu',
        'thecarbonunderground.org',
        'speedgoat.com',
        'hotelunique.com',
        'shareindia.com',
        'techcrunch.com',
        'example.com', 
        'github.com',
        'stackoverflow.com',
        'reddit.com',
        'elmleynaturereserve.co.uk',
        'aooke-anime.com',
        'freetronics.com.au',
        'roell.net',
        'tongitsfun.xyz',
        'autoeurope.eu',
        'thecarbonunderground.org',
        'speedgoat.com',
        'hotelunique.com',
        'shareindia.com',
    ]
    
    # Build batch payload with proxies
    batch_domains = []
    
    for i, domain in enumerate(domains):
        # Assign proxy (rotate through proxy list)
        proxy_idx = i % len(proxies)
        proxy = proxies[proxy_idx]
        
        batch_domains.append({
            'domain': domain,
            'proxy_ip': proxy['proxy_ip'],
            'proxy_port': proxy['proxy_port'],
            'proxy_user': proxy['proxy_user'],
            'proxy_pass': proxy['proxy_pass']
        })
    
    print(f"📦 Submitting batch of {len(domains)} domains with proxies...\n")
    print(f"   Using {len(proxies)} unique proxies (rotating)\n")
    
    response = requests.post(
        f"{SERVER_URL}/batch",
        json={'domains': batch_domains}
    )
    
    result = response.json()
    print(f"✅ {result['message']}")
    print(f"Task IDs: {result['task_ids'][:2]}... ({len(result['task_ids'])} total)\n")
    
    return result['task_ids']

def monitor_progress(task_ids):
    """Monitor queue and job status"""
    
    print("📊 Monitoring queue (press Ctrl+C to stop)...\n")
    print("-" * 80)
    
    try:
        while True:
            # Get queue status
            queue_resp = requests.get(f"{SERVER_URL}/queue")
            queue_data = queue_resp.json()
            
            # Get health/stats
            health_resp = requests.get(f"{SERVER_URL}/health")
            health_data = health_resp.json()
            
            # Clear previous output (optional)
            print(f"\r📊 Queue: {queue_data['queue_size']} | " +
                  f"Processing: {queue_data['processing_count']} | " +
                  f"Queued: {health_data['queued']} | " +
                  f"Completed: {health_data['completed']} | " +
                  f"Failed: {health_data['failed']}", end="")
            
            # Check if all done
            if health_data['completed'] + health_data['failed'] >= len(task_ids):
                print("\n\n✅ All tasks completed!")
                break
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\n⏸️  Monitoring stopped\n")

def show_results(task_ids):
    """Show final results"""
    
    print("\n" + "=" * 80)
    print("📋 FINAL RESULTS")
    print("=" * 80 + "\n")
    
    completed_count = 0
    failed_count = 0
    
    for i, task_id in enumerate(task_ids):
        result_resp = requests.get(f"{SERVER_URL}/result/{task_id}")
        result_data = result_resp.json()
        
        status = result_data['status']
        domain = result_data['domain']
        
        status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
        
        # Show domain with proxy info
        proxy_info = ""
        if 'proxy' in result_data and result_data['proxy']:
            proxy_ip = result_data['proxy'].split('//')[1].split(':')[0] if '//' in result_data['proxy'] else result_data['proxy'].split(':')[0]
            proxy_info = f" [proxy: {proxy_ip}]"
        
        print(f"{status_icon} {domain}{proxy_info}: {status}")
        
        if status == "completed":
            completed_count += 1
            if 'result' in result_data:
                metrics = result_data['result']
                print(f"   DR: {metrics.get('_dr')}, " +
                      f"Backlinks: {metrics.get('backlinks')}, " +
                      f"Linking: {metrics.get('linking_websites')}")
        elif status == "failed":
            failed_count += 1
            error_msg = result_data.get('error', 'Unknown error')
            # Truncate long errors
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            print(f"   Error: {error_msg}")
        
        print()
    
    print("=" * 80)
    print(f"📊 SUMMARY: {completed_count} completed, {failed_count} failed out of {len(task_ids)} total")
    print("=" * 80)

def main():
    """Main function"""
    start_time = time.time()
    
    # Submit batch with proxies
    task_ids = submit_batch_with_proxies()
    
    if not task_ids:
        return
    
    # Monitor progress
    monitor_progress(task_ids)
    
    # Show results
    show_results(task_ids)
    
    end_time = time.time()
    print(f"\n⏱️  Total time: {end_time - start_time:.2f} seconds")
    print(f"⚡ Average per domain: {(end_time - start_time) / len(task_ids):.2f} seconds\n")

if __name__ == '__main__':
    main()

