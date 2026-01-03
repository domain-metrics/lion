#!/usr/bin/env python3
"""
Test script demonstrating the new server.py approach:
- WITH proxy: New context + new page (for isolation)
- WITHOUT proxy: Shared context + pages only (Test 4 approach - NO semaphore)

This matches Test 4 which achieved 100% success (30/30 tasks)
"""

import asyncio
import time
from camoufox import AsyncCamoufox

# Configuration
NUM_TASKS = 30
AHREFS_URL = "https://ahrefs.com/website-authority-checker/"

print("=" * 80)
print("🧪 Testing Server.py Strategy")
print("=" * 80)
print(f"Tasks: {NUM_TASKS}")
print(f"Target: {AHREFS_URL}")
print()
print("Strategy:")
print("  WITHOUT proxy: Shared context + pages only (NO semaphore)")
print("  WITH proxy: New context + new page per task")
print("=" * 80)
print()


async def test_without_proxy():
    """Test WITHOUT proxy: Shared context + multiple pages (NO semaphore)"""
    print("\n" + "=" * 80)
    print(f"TEST 1: WITHOUT PROXY - Shared Context + Pages ({NUM_TASKS} tasks)")
    print("Expected: 100% success (like Test 4)")
    print("=" * 80)
    
    start_time = time.time()
    success_count = 0
    failed_count = 0
    
    async with AsyncCamoufox(headless=False) as browser:
        # Create ONE shared context
        context = await browser.new_context()
        print("✅ Created shared context")
        
        async def load_page(i):
            """Load a page in the shared context"""
            nonlocal success_count, failed_count
            
            try:
                print(f"  [{i:2d}] Creating page...")
                # NO semaphore - direct page creation (Test 4 approach)
                page = await context.new_page()
                print(f"  [{i:2d}] ✓ Page created, loading URL...")
                
                await page.goto(AHREFS_URL, timeout=15000)
                title = await page.title()
                print(f"  [{i:2d}] ✅ SUCCESS: '{title[:50]}...'")
                
                await page.close()
                success_count += 1
                
            except asyncio.TimeoutError:
                print(f"  [{i:2d}] ⏰ TIMEOUT")
                failed_count += 1
            except Exception as e:
                print(f"  [{i:2d}] ❌ ERROR: {e}")
                failed_count += 1
        
        # Run all tasks concurrently
        await asyncio.gather(*[load_page(i) for i in range(NUM_TASKS)])
        
        # Close shared context
        await context.close()
    
    duration = time.time() - start_time
    
    print("\n" + "=" * 80)
    print(f"✅ Test 1 Complete: {success_count}/{NUM_TASKS} succeeded ({success_count/NUM_TASKS*100:.1f}%)")
    print(f"❌ Failed: {failed_count}")
    print(f"⏱️  Duration: {duration:.1f}s")
    print(f"📊 Avg per task: {duration/NUM_TASKS:.1f}s")
    print("=" * 80)


async def test_with_proxy():
    """Test WITH proxy: New context + new page per task"""
    print("\n" + "=" * 80)
    print(f"TEST 2: WITH PROXY - New Context + Page per Task ({NUM_TASKS} tasks)")
    print("Expected: Works with proxy isolation")
    print("=" * 80)
    
    # Example proxy (replace with real proxy for actual testing)
    proxy_template = {
        "server": "http://proxy-server:port",
        "username": "user",
        "password": "pass"
    }
    
    start_time = time.time()
    success_count = 0
    failed_count = 0
    
    async with AsyncCamoufox(headless=False) as browser:
        
        async def load_with_proxy(i):
            """Load with a new context (proxy isolation)"""
            nonlocal success_count, failed_count
            
            try:
                print(f"  [{i:2d}] Creating context with proxy...")
                # Create new context per task (for proxy isolation)
                context = await browser.new_context(proxy=proxy_template)
                print(f"  [{i:2d}] ✓ Context created, creating page...")
                
                page = await context.new_page()
                print(f"  [{i:2d}] ✓ Page created, loading URL...")
                
                # Note: This will fail with fake proxy, but demonstrates the approach
                await page.goto(AHREFS_URL, timeout=15000)
                title = await page.title()
                print(f"  [{i:2d}] ✅ SUCCESS: '{title[:50]}...'")
                
                await page.close()
                await context.close()
                success_count += 1
                
            except asyncio.TimeoutError:
                print(f"  [{i:2d}] ⏰ TIMEOUT (expected with fake proxy)")
                failed_count += 1
            except Exception as e:
                print(f"  [{i:2d}] ❌ ERROR: {e} (expected with fake proxy)")
                failed_count += 1
        
        # Run all tasks concurrently
        await asyncio.gather(*[load_with_proxy(i) for i in range(NUM_TASKS)])
    
    duration = time.time() - start_time
    
    print("\n" + "=" * 80)
    print(f"✅ Test 2 Complete: {success_count}/{NUM_TASKS} succeeded ({success_count/NUM_TASKS*100:.1f}%)")
    print(f"❌ Failed: {failed_count} (expected with fake proxy)")
    print(f"⏱️  Duration: {duration:.1f}s")
    print(f"📊 Avg per task: {duration/NUM_TASKS:.1f}s")
    print("=" * 80)


async def main():
    """Run both tests"""
    print("\n🚀 Starting Tests...\n")
    
    # Test 1: WITHOUT proxy (should work perfectly like Test 4)
    await test_without_proxy()
    
    print("\n\n⏸️  Pausing 5 seconds before next test...\n")
    await asyncio.sleep(5)
    
    # Test 2: WITH proxy (demonstrates approach, will fail with fake proxy)
    print("\n📝 Note: Test 2 will fail because we're using a fake proxy.")
    print("   Replace proxy_template with real proxy credentials to test properly.\n")
    # Uncomment to run proxy test:
    # await test_with_proxy()
    
    print("\n" + "=" * 80)
    print("🎉 ALL TESTS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

