#!/usr/bin/env python3
"""
API Test Script
Tests both proxy and non-proxy batch processing with 20 domains each
"""

import requests
import time
from pathlib import Path

# Configuration
API_URL = "http://127.0.0.1:5001"
PROXY_FILE = "../Webshare 100 proxies.txt"

# Test domains (20 domains for each test)
TEST_DOMAINS = [
    "example.com", "stackoverflow.com", "github.com", "reddit.com", "wikipedia.org",
    "amazon.com", "twitter.com", "linkedin.com", "youtube.com", "facebook.com",
    "netflix.com", "spotify.com", "apple.com", "microsoft.com", "google.com",
    "instagram.com", "tiktok.com", "pinterest.com", "tumblr.com", "medium.com"
]

def load_proxies(count):
    """Load multiple proxies from Webshare file"""
    proxy_path = Path(__file__).parent / PROXY_FILE
    proxies = []
    
    if proxy_path.exists():
        with open(proxy_path, 'r') as f:
            for i, line in enumerate(f):
                if i >= count:
                    break
                proxy = line.strip()
                if proxy:
                    proxies.append(proxy)
    
    return proxies

def clear_queue_and_results():
    """Clear queue and results before testing"""
    print("🧹 Clearing queue and results...")
    try:
        requests.post(f"{API_URL}/queue/clear")
        requests.post(f"{API_URL}/results/clear")
        print("   ✅ Cleared\n")
    except Exception as e:
        print(f"   ⚠️  Error: {e}\n")

def scale_workers(count, proxies=None):
    """Scale workers to specified count with optional proxy assignments"""
    print(f"⚙️  Scaling to {count} workers...")
    
    if proxies:
        print(f"   🔒 With {len(proxies)} proxies")
    
    try:
        if proxies:
            # POST with proxies
            response = requests.post(
                f"{API_URL}/scale",
                json={'scale': count, 'proxies': proxies},
                headers={'Content-Type': 'application/json'}
            )
        else:
            # GET without proxies
            response = requests.get(f"{API_URL}/scale", params={'scale': count})
        
        data = response.json()
        print(f"   ✅ {data.get('message', 'Scaled')}")
        print(f"   📊 Active workers: {data.get('active_workers', 0)}")
        
        if proxies and 'proxies_assigned' in data:
            print(f"   🔒 Proxies assigned: {len([p for p in data['proxies_assigned'] if p != 'no proxy'])}\n")
        else:
            print()
        
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}\n")
        return False

def submit_batch(domains, test_name="Test"):
    """Submit batch of domains (workers already have proxies)"""
    print(f"📤 Submitting {len(domains)} domains ({test_name})...")
    
    payload = {'domains': domains}
    
    try:
        response = requests.post(
            f"{API_URL}/batch",
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ {data.get('message', 'Submitted')}")
            print(f"   📊 Queue length: {data.get('queue_length', 0)}\n")
            return True
        else:
            print(f"   ❌ Error: {response.status_code} - {response.text}\n")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}\n")
        return False

def monitor_progress():
    """Monitor queue progress"""
    print("⏳ Monitoring progress...")
    start_time = time.time()
    last_completed = 0
    
    while True:
        try:
            # Get queue status
            queue_response = requests.get(f"{API_URL}/queue")
            queue_data = queue_response.json()
            
            queue_length = queue_data.get('queue_length', 0)
            processing_count = queue_data.get('processing_count', 0)
            
            # Get results
            results_response = requests.get(f"{API_URL}/results")
            results_data = results_response.json()
            
            completed = len(results_data.get('completed', []))
            failed = len(results_data.get('failed', []))
            total = completed + failed
            
            # Print progress if changed
            if completed != last_completed or processing_count > 0 or queue_length > 0:
                elapsed = time.time() - start_time
                print(f"   ⏱️  {elapsed:.0f}s | Queue: {queue_length} | Processing: {processing_count} | Completed: {completed} | Failed: {failed}")
                last_completed = completed
            
            # Check if done
            if queue_length == 0 and processing_count == 0 and total > 0:
                print(f"   ✅ Processing complete!\n")
                break
            
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\n   ⚠️  Monitoring interrupted\n")
            break
        except Exception as e:
            print(f"   ⚠️  Monitor error: {e}")
            time.sleep(2)

def get_results():
    """Get and display results"""
    print("📊 Fetching results...")
    try:
        response = requests.get(f"{API_URL}/results")
        data = response.json()
        
        completed = data.get('completed', [])
        failed = data.get('failed', [])
        
        print(f"   ✅ Completed: {len(completed)}")
        print(f"   ❌ Failed: {len(failed)}")
        print(f"   📈 Total: {len(completed) + len(failed)}\n")
        
        # Show sample of completed results
        if completed:
            print("   📝 Sample completed results:")
            for i, result in enumerate(completed[:5], 1):
                domain = result.get('domain', 'N/A')
                dr = result.get('dr', 'N/A')
                backlinks = result.get('backlinks', 'N/A')
                linking = result.get('linking_websites', 'N/A')
                elapsed = result.get('elapsed', 0)
                print(f"      {i}. {domain:25s} | DR: {str(dr):>4} | Backlinks: {str(backlinks):>8} | Linking: {str(linking):>6} | Time: {elapsed:.1f}s")
            
            if len(completed) > 5:
                print(f"      ... and {len(completed) - 5} more")
            print()
        
        # Show failed if any
        if failed:
            print("   ⚠️  Failed domains:")
            for i, result in enumerate(failed[:5], 1):
                domain = result.get('domain', 'N/A')
                error = result.get('error', 'Unknown error')[:50]
                print(f"      {i}. {domain:25s} | Error: {error}")
            
            if len(failed) > 5:
                print(f"      ... and {len(failed) - 5} more")
            print()
        
        return completed, failed
        
    except Exception as e:
        print(f"   ❌ Error: {e}\n")
        return [], []

def run_test():
    """Run the complete test"""
    print("=" * 80)
    print("🧪 API TEST SCRIPT - Proxy-Per-Worker Model")
    print("=" * 80)
    print()
    
    # Step 1: Clear previous data
    clear_queue_and_results()
    
    # Step 2: Load proxies
    proxies = load_proxies(3)
    
    # =========================================================================
    # TEST 1: Without Proxy (3 workers, no proxy)
    # =========================================================================
    print("=" * 80)
    print("TEST 1: WITHOUT PROXY (3 workers, 20 domains)")
    print("=" * 80)
    print()
    
    if not scale_workers(3):
        print("❌ Failed to scale workers. Make sure Flask server is running.")
        return
    
    # Wait for workers to initialize
    time.sleep(3)
    
    if submit_batch(TEST_DOMAINS, test_name="No Proxy"):
        monitor_progress()
        completed_no_proxy, failed_no_proxy = get_results()
        
        print(f"✅ TEST 1 COMPLETE: {len(completed_no_proxy)} completed, {len(failed_no_proxy)} failed\n")
    else:
        print("❌ TEST 1 FAILED: Could not submit batch\n")
    
    # Wait a bit between tests
    time.sleep(5)
    
    # =========================================================================
    # TEST 2: With Proxy (3 workers with 3 proxies)
    # =========================================================================
    print("=" * 80)
    print("TEST 2: WITH PROXY (3 workers with proxies, 20 domains)")
    print("=" * 80)
    print()
    
    # Clear results for second test
    clear_queue_and_results()
    
    # Scale down first
    scale_workers(0)
    time.sleep(2)
    
    if proxies and len(proxies) >= 3:
        # Scale up with proxies
        if not scale_workers(3, proxies=proxies[:3]):
            print("❌ Failed to scale workers with proxies.")
            return
        
        # Wait for workers to initialize
        time.sleep(3)
        
        if submit_batch(TEST_DOMAINS, test_name="With Proxy"):
            monitor_progress()
            completed_proxy, failed_proxy = get_results()
            
            print(f"✅ TEST 2 COMPLETE: {len(completed_proxy)} completed, {len(failed_proxy)} failed\n")
        else:
            print("❌ TEST 2 FAILED: Could not submit batch\n")
    else:
        print("⚠️  TEST 2 SKIPPED: Need at least 3 proxies in Webshare file\n")
        completed_proxy = []
        failed_proxy = []
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print()
    print(f"Test 1 (No Proxy):   {len(completed_no_proxy)} completed, {len(failed_no_proxy)} failed")
    if proxies and len(proxies) >= 3:
        print(f"Test 2 (With Proxy): {len(completed_proxy)} completed, {len(failed_proxy)} failed")
    else:
        print(f"Test 2 (With Proxy): SKIPPED (need 3 proxies)")
    print()
    print("=" * 80)
    print("✅ ALL TESTS COMPLETE!")
    print("=" * 80)

if __name__ == '__main__':
    try:
        run_test()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")

