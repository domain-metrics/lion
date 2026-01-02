#!/usr/bin/env python3
"""
Example: How to use proxies with the scraper API
"""

import requests
import time

MAC_SCRAPER_URL = "http://127.0.0.1:8000"

# Example 1: Single domain with proxy
def example_single_with_proxy():
    print("=== Example 1: Single domain with proxy ===\n")
    
    response = requests.post(
        f"{MAC_SCRAPER_URL}/scrape",
        json={
            'domain': 'example.com',
            'proxy_ip': '192.168.1.100',
            'proxy_port': '8080',
            'proxy_user': 'myusername',
            'proxy_pass': 'mypassword'
        }
    )
    
    result = response.json()
    print(f"Task ID: {result['task_id']}")
    print(f"Status: {result['status']}")
    print(f"Proxy: {result.get('proxy')}\n")
    
    return result['task_id']


# Example 2: Single domain without proxy
def example_single_without_proxy():
    print("=== Example 2: Single domain without proxy ===\n")
    
    response = requests.post(
        f"{MAC_SCRAPER_URL}/scrape",
        json={
            'domain': 'example.org'
        }
    )
    
    result = response.json()
    print(f"Task ID: {result['task_id']}")
    print(f"Status: {result['status']}")
    print(f"Proxy: {result.get('proxy')}\n")
    
    return result['task_id']


# Example 3: Batch with multiple proxies
def example_batch_with_proxies():
    print("=== Example 3: Batch scraping with different proxies ===\n")
    
    response = requests.post(
        f"{MAC_SCRAPER_URL}/batch",
        json={
            'domains': [
                {
                    'domain': 'example.com',
                    'proxy_ip': '192.168.1.100',
                    'proxy_port': '8080',
                    'proxy_user': 'user1',
                    'proxy_pass': 'pass1'
                },
                {
                    'domain': 'example.org',
                    'proxy_ip': '192.168.1.101',
                    'proxy_port': '8080',
                    'proxy_user': 'user2',
                    'proxy_pass': 'pass2'
                },
                {
                    'domain': 'example.net'
                    # No proxy for this one
                }
            ]
        }
    )
    
    result = response.json()
    print(f"Message: {result['message']}")
    print(f"Task IDs: {result['task_ids']}\n")
    
    return result['task_ids']


# Example 4: Reading proxy list from file
def example_batch_from_file():
    print("=== Example 4: Batch with proxies from file ===\n")
    
    # Read proxy list (format: ip:port:user:pass)
    # Example file content:
    # 192.168.1.100:8080:user1:pass1
    # 192.168.1.101:8080:user2:pass2
    
    domains = ['example.com', 'example.org', 'example.net']
    
    # Read proxies from file
    try:
        with open('Webshare 100 proxies.txt', 'r') as f:
            proxies = []
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(':')
                if len(parts) >= 4:
                    proxies.append({
                        'ip': parts[0],
                        'port': parts[1],
                        'user': parts[2],
                        'pass': parts[3]
                    })
        
        # Build batch payload
        batch_domains = []
        for i, domain in enumerate(domains):
            if i < len(proxies):
                proxy = proxies[i]
                batch_domains.append({
                    'domain': domain,
                    'proxy_ip': proxy['ip'],
                    'proxy_port': proxy['port'],
                    'proxy_user': proxy['user'],
                    'proxy_pass': proxy['pass']
                })
            else:
                # No more proxies, submit without proxy
                batch_domains.append({'domain': domain})
        
        response = requests.post(
            f"{MAC_SCRAPER_URL}/batch",
            json={'domains': batch_domains}
        )
        
        result = response.json()
        print(f"Message: {result['message']}")
        print(f"Task IDs: {result['task_ids']}\n")
        
        return result['task_ids']
        
    except FileNotFoundError:
        print("Proxy file not found. Using example without proxies.\n")
        return None


# Check result
def check_result(task_id):
    print(f"Checking result for {task_id}...")
    
    for _ in range(10):
        response = requests.get(f"{MAC_SCRAPER_URL}/result/{task_id}")
        result = response.json()
        
        status = result['status']
        print(f"  Status: {status}")
        
        if status == 'completed':
            print(f"  Result: {result['result']}")
            break
        elif status == 'failed':
            print(f"  Error: {result.get('error')}")
            break
        
        time.sleep(2)
    
    print()


if __name__ == '__main__':
    print("🔍 Proxy Examples for Ahrefs Scraper\n")
    
    # Run examples
    # task_id = example_single_with_proxy()
    # check_result(task_id)
    
    # task_id = example_single_without_proxy()
    # check_result(task_id)
    
    # task_ids = example_batch_with_proxies()
    # for task_id in task_ids[:1]:  # Check first result
    #     check_result(task_id)
    
    task_ids = example_batch_from_file()
    if task_ids:
        for task_id in task_ids[:1]:  # Check first result
            check_result(task_id)

