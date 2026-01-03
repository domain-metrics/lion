#!/usr/bin/env python3
"""
Direct scraping test (NO Flask)

Tests concurrent scraping with N workers directly using asyncio.
Reads domains from domains_100.txt and processes them.
"""

import asyncio
import time
from datetime import datetime

# Import helpers
from camoufox_helper import initialize_browser, close_browser, get_context_pool_stats
from ahrefs_helper import scrape_ahrefs_domain

# Configuration
MAX_CONCURRENT_WORKERS = 3  # Set to 0 to process ALL domains, or N to limit to first N domains
DOMAINS_FILE = "domains_100.txt"
USE_PROXIES = False  # Set to True to use proxies, False to test without proxies

# Results storage
results = []
failed = []


def load_domains(filename):
    """Load domains from file"""
    try:
        with open(filename, 'r') as f:
            domains = [line.strip() for line in f if line.strip()]
        print(f"✅ Loaded {len(domains)} domains from {filename}")
        return domains
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
        print(f"📝 Creating sample file with 10 domains...")
        
        # Create sample file
        sample_domains = [
            'techcrunch.com',
            'github.com',
            'stackoverflow.com',
            'reddit.com',
            'example.com',
            'npmjs.com',
            'python.org',
            'nodejs.org',
            'mozilla.org',
            'wikipedia.org'
        ]
        
        with open(filename, 'w') as f:
            for domain in sample_domains:
                f.write(f"{domain}\n")
        
        print(f"✅ Created {filename} with {len(sample_domains)} sample domains")
        return sample_domains


def load_proxies(filename="Webshare 100 proxies.txt"):
    """Load proxies from file (optional)"""
    try:
        proxies = []
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Format: ip:port:user:pass
                parts = line.split(':')
                if len(parts) >= 4:
                    proxies.append({
                        'server': f"http://{parts[0]}:{parts[1]}",
                        'username': parts[2],
                        'password': parts[3]
                    })
        
        print(f"✅ Loaded {len(proxies)} proxies from {filename}")
        return proxies
    except FileNotFoundError:
        print(f"⚠️  No proxy file found: {filename}")
        return []


async def scrape_domain_task(idx, domain, use_proxy=False, proxies=None):
    """
    Scrape a single domain (Test 4 approach - NO semaphore)
    
    Args:
        idx: Domain index
        domain: Domain to scrape
        use_proxy: Whether to use proxies
        proxies: List of proxies (if use_proxy is True)
    
    Returns:
        tuple: (success, result_or_error_dict)
    """
    print(f"[{idx:3d}] 🔄 Processing {domain}")
    start_time = time.time()
    
    # Get proxy if enabled
    proxy = None
    if use_proxy and proxies:
        proxy = proxies[(idx - 1) % len(proxies)]
        print(f"[{idx:3d}]    🔒 Using proxy: {proxy['server']}")
    
    try:
        # Scrape the domain (NO semaphore - Test 4 approach!)
        result = await scrape_ahrefs_domain(domain, proxy)
        
        elapsed = time.time() - start_time
        print(f"[{idx:3d}] ✅ Completed {domain} in {elapsed:.1f}s")
        print(f"[{idx:3d}]    DR: {result['_dr']}, Backlinks: {result['backlinks']}, Linking: {result['linking_websites']}")
        
        return (True, {
            'domain': domain,
            'result': result,
            'elapsed': elapsed,
            'idx': idx
        })
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[{idx:3d}] ❌ Failed {domain} in {elapsed:.1f}s - {e}")
        
        return (False, {
            'domain': domain,
            'error': str(e),
            'elapsed': elapsed,
            'idx': idx
        })


async def main():
    """Main async function"""
    global results, failed
    
    print("=" * 80)
    print("🧪 Direct Scraping Test (NO Flask)")
    print("=" * 80)
    print(f"Concurrent Limit: {MAX_CONCURRENT_WORKERS if MAX_CONCURRENT_WORKERS > 0 else 'ALL'}")
    print(f"Approach: Test 4 + Semaphores (context/page creation serialized)")
    print(f"Bug Fix: Camoufox issue #279 (deadlock prevention)")
    print("=" * 80)
    print()
    
    # Load domains
    domains = load_domains(DOMAINS_FILE)
    
    if not domains:
        print("❌ No domains to process")
        return
    
    # Load proxies (optional)
    if USE_PROXIES:
        proxies = load_proxies()
        use_proxy = len(proxies) > 0
        if use_proxy:
            print(f"🔒 Proxy mode: ENABLED ({len(proxies)} proxies available)")
        else:
            print(f"🌐 Proxy mode: DISABLED (no proxies found)")
    else:
        proxies = []
        use_proxy = False
        print(f"🌐 Proxy mode: DISABLED (USE_PROXIES=False)")
    
    print()
    input("Press Enter to start scraping...")
    print()
    
    # Initialize browser
    print("🚀 Initializing browser...")
    await initialize_browser()
    print()
    
    total = len(domains)
    
    # Limit domains if MAX_CONCURRENT_WORKERS is set
    if MAX_CONCURRENT_WORKERS > 0 and MAX_CONCURRENT_WORKERS < total:
        print(f"⚠️  Limiting to first {MAX_CONCURRENT_WORKERS} domains (set MAX_CONCURRENT_WORKERS=0 for all)")
        domains = domains[:MAX_CONCURRENT_WORKERS]
        total = len(domains)
        print()
    
    # Create tasks for all domains (Test 4 approach - NO semaphore!)
    print(f"🚀 Starting {total} concurrent tasks (Test 4: NO semaphore)...")
    start_time = time.time()
    
    tasks = []
    for idx, domain in enumerate(domains, 1):
        task = scrape_domain_task(idx, domain, use_proxy, proxies)
        tasks.append(task)
    
    # Run ALL tasks concurrently using asyncio.gather (like Test 4)
    task_results = await asyncio.gather(*tasks, return_exceptions=False)
    
    # Process results
    for success, data in task_results:
        if success:
            results.append(data)
        else:
            failed.append(data)
    
    # Calculate stats
    elapsed_total = time.time() - start_time
    
    print()
    print("=" * 80)
    print("📊 RESULTS")
    print("=" * 80)
    print(f"✅ Completed: {len(results)}/{total}")
    print(f"❌ Failed: {len(failed)}/{total}")
    print(f"⏱️  Total time: {elapsed_total:.1f}s")
    print(f"📈 Average per domain: {elapsed_total/total:.1f}s")
    print(f"🚀 Throughput: {total/elapsed_total:.2f} domains/sec")
    print()
    
    # Show context pool stats
    stats = get_context_pool_stats()
    print(f"🔧 Context pool stats:")
    print(f"   No-proxy context: {stats['no_proxy_context']}")
    print(f"   Proxy contexts: {stats['proxy_contexts']}")
    print(f"   Total contexts: {stats['total_contexts']}")
    print()
    
    # Show some results
    if results:
        print("📋 Sample Results (first 5):")
        for r in results[:5]:
            print(f"   {r['domain']}: DR={r['result']['_dr']}, "
                  f"Backlinks={r['result']['backlinks']}, "
                  f"Time={r['elapsed']:.1f}s")
        print()
    
    # Show failures
    if failed:
        print("❌ Failures:")
        for f in failed[:10]:  # Show first 10
            error_short = f['error'][:60] + "..." if len(f['error']) > 60 else f['error']
            print(f"   {f['domain']}: {error_short}")
        print()
    
    # Close browser
    print("🔒 Closing browser...")
    await close_browser()
    
    print("=" * 80)
    print("✅ Test Complete!")
    print("=" * 80)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏸️  Interrupted by user")

