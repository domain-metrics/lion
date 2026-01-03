#!/usr/bin/env python3
"""
Test script for run2.py - Simple concurrent page loading
"""

import requests
import time

BASE_URL = "http://localhost:5001"

def test_single_load():
    """Test single domain load"""
    print("=" * 80)
    print("Test 1: Single Domain Load")
    print("=" * 80)
    
    response = requests.post(f"{BASE_URL}/load", json={
        'domain': 'example.com'
    })
    
    print(f"Response: {response.json()}")
    print()


def test_batch_load():
    """Test batch domain load"""
    print("=" * 80)
    print("Test 2: Batch Domain Load (5 domains)")
    print("=" * 80)
    
    domains = [
        'example.com',
        'github.com',
        'stackoverflow.com',
        'python.org',
        'nodejs.org'
    ]
    
    response = requests.post(f"{BASE_URL}/batch", json={
        'domains': domains
    })
    
    print(f"Response: {response.json()}")
    print()


def test_with_proxy():
    """Test with proxy"""
    print("=" * 80)
    print("Test 3: Load with Proxy")
    print("=" * 80)
    
    # Read first proxy from file
    try:
        with open('Webshare 100 proxies.txt', 'r') as f:
            first_proxy = f.readline().strip()
        
        response = requests.post(f"{BASE_URL}/load", json={
            'domain': 'example.com',
            'proxy': first_proxy
        })
        
        print(f"Proxy: {first_proxy}")
        print(f"Response: {response.json()}")
    except FileNotFoundError:
        print("⚠️  Proxy file not found, skipping proxy test")
    
    print()


def monitor_queue(duration=30):
    """Monitor queue status for specified duration"""
    print("=" * 80)
    print(f"Monitoring Queue (for {duration}s)")
    print("=" * 80)
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        response = requests.get(f"{BASE_URL}/queue")
        data = response.json()
        
        print(f"[{time.time() - start_time:6.1f}s] "
              f"Queue: {data['queue_length']:2d} | "
              f"Processing: {data['processing_count']}/{data['max_concurrent']} | "
              f"Completed: {data['completed_count']:2d} | "
              f"Failed: {data['failed_count']:2d}")
        
        # Stop if nothing in queue and nothing processing
        if data['queue_length'] == 0 and data['processing_count'] == 0:
            print("\n✅ All tasks completed!")
            break
        
        time.sleep(2)
    
    print()


def get_results():
    """Get final results"""
    print("=" * 80)
    print("Final Results")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/results")
    data = response.json()
    
    print(f"\nTotal: {data['total']}")
    print(f"Completed: {len(data['completed'])}")
    print(f"Failed: {len(data['failed'])}")
    
    if data['completed']:
        print("\n✅ Completed:")
        for result in data['completed']:
            print(f"   {result['domain']:30s} - {result['elapsed']:5.1f}s - {result['title'][:40]}")
    
    if data['failed']:
        print("\n❌ Failed:")
        for result in data['failed']:
            error = result.get('error', 'Unknown error')[:60]
            print(f"   {result['domain']:30s} - {error}")
    
    print()


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🧪 Testing run2.py - Simple Concurrent Page Loading")
    print("=" * 80)
    print()
    
    # Wait for server to be ready
    print("⏳ Waiting for server to be ready...")
    for i in range(10):
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                print("✅ Server is ready!\n")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("❌ Server not responding. Please start run2.py first:")
        print("   python3 run2.py")
        exit(1)
    
    # Run tests
    test_batch_load()
    time.sleep(2)
    monitor_queue(duration=60)
    get_results()
    
    print("=" * 80)
    print("✅ Test Complete!")
    print("=" * 80)

