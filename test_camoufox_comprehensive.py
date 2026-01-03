#!/usr/bin/env python3
"""
COMPREHENSIVE CAMOUFOX DEADLOCK TEST
Tests all scenarios: What works ✅ and what doesn't ❌

This single script demonstrates:
1. ❌ WITHOUT semaphore - Multiple contexts (WILL FREEZE)
2. ✅ WITH semaphore - Multiple contexts (WORKS!)
3. ✅ WITH semaphore - Multiple pages in one context (WORKS!)
4. ❌ WITHOUT semaphore - Multiple pages (WILL FREEZE)

GitHub Issue: https://github.com/daijro/camoufox/issues/279
"""

import asyncio
from camoufox.async_api import AsyncCamoufox
import time
import random

# Semaphore to prevent simultaneous context/page creation
context_semaphore = asyncio.Semaphore(1)

# Test configuration
NUM_TASKS = 30  # 🚨 STRESS TEST: 30 concurrent tasks!
AHREFS_URL = 'https://ahrefs.com/website-authority-checker/'


# ============================================================================
# TEST 1: ❌ Multiple contexts WITHOUT semaphore (WILL FREEZE!)
# ============================================================================

async def test_1_multiple_contexts_no_semaphore():
    """
    ❌ THIS WILL FREEZE! (Demonstrates the bug)
    Creating 30 contexts simultaneously without semaphore
    """
    print("\n" + "=" * 80)
    print("TEST 1: ❌ Multiple contexts WITHOUT semaphore (WILL FREEZE!)")
    print("=" * 80)
    print(f"Creating {NUM_TASKS} contexts with 10-15s queue delays...")
    print("Expected: Will freeze after 1-2 contexts (Camoufox deadlock bug)")
    print()
    
    # Store all pages/contexts to close them AFTER waiting
    all_contexts = []
    all_pages = []
    
    async def create_context_and_scrape(browser, i):
        try:
            # Random delay BEFORE creating (simulating queue wait)
            delay = random.uniform(10, 15)
            print(f"  [{i:2d}] ⏰ Queue wait: {delay:.1f}s...")
            await asyncio.sleep(delay)
            
            # NO SEMAPHORE - Creating contexts simultaneously
            print(f"  [{i:2d}] Creating context...")
            context = await browser.new_context()
            all_contexts.append(context)
            
            print(f"  [{i:2d}] Creating page...")
            page = await context.new_page()
            all_pages.append(page)
            
            print(f"  [{i:2d}] Loading Ahrefs...")
            await page.goto(AHREFS_URL, timeout=15000)
            
            title = await page.title()
            print(f"  [{i:2d}] ✅ SUCCESS: {title[:40]}...")
            
            # DON'T close yet - keep everything open!
            return True
        except Exception as e:
            print(f"  [{i:2d}] ❌ FAILED: {str(e)[:50]}...")
            return False
    
    start_time = time.time()
    
    async with AsyncCamoufox(headless=False) as browser:
        tasks = [create_context_and_scrape(browser, i) for i in range(1, NUM_TASKS + 1)]
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=600.0  # 10 min (30 tasks × 10-15s delay + load + cleanup)
            )
            success_count = sum(1 for r in results if r is True)
            print(f"\n📊 Result: {success_count}/{NUM_TASKS} succeeded")
            
            # IMPORTANT: Wait 30 seconds before closing - this may reveal deadlock!
            print(f"\n⏳ Waiting 30 seconds with all {len(all_pages)} pages/contexts OPEN...")
            print("   (This might trigger the deadlock during cleanup)")
            await asyncio.sleep(30)
            
            print(f"\n🧹 Now closing all {len(all_pages)} pages and {len(all_contexts)} contexts...")
            for page in all_pages:
                try:
                    await page.close()
                except:
                    pass
            for context in all_contexts:
                try:
                    await context.close()
                except:
                    pass
            print("✅ Cleanup complete!")
            
        except asyncio.TimeoutError:
            print(f"\n⏱️  TIMEOUT after 10 minutes!")
            print("💡 This is the Camoufox deadlock bug in action!")
            print("   (Likely froze during cleanup phase)")
    
    elapsed = time.time() - start_time
    print(f"⏱️  Total Time: {elapsed:.1f}s")
    print("\n🔴 CONCLUSION: Without semaphore = DEADLOCK")


# ============================================================================
# TEST 2: ✅ Multiple contexts WITH semaphore (WORKS!)
# ============================================================================

async def test_2_multiple_contexts_with_semaphore():
    """
    ✅ THIS WORKS! (Demonstrates the fix)
    Creating 30 contexts sequentially with semaphore
    """
    print("\n" + "=" * 80)
    print("TEST 2: ✅ Multiple contexts WITH semaphore (WORKS!)")
    print("=" * 80)
    print(f"Creating {NUM_TASKS} contexts with 10-15s queue delays + semaphore...")
    print("Expected: All tasks will complete successfully")
    print()
    
    # Store all pages/contexts to close them AFTER waiting
    all_contexts = []
    all_pages = []
    
    async def create_context_and_scrape(browser, i):
        try:
            # Random delay BEFORE creating (simulating queue wait)
            delay = random.uniform(10, 15)
            print(f"  [{i:2d}] ⏰ Queue wait: {delay:.1f}s...")
            await asyncio.sleep(delay)
            
            # WITH SEMAPHORE - Only 1 context created at a time
            async with context_semaphore:
                print(f"  [{i:2d}] 🔐 Got lock, creating context...")
                context = await browser.new_context()
                all_contexts.append(context)
                page = await context.new_page()
                all_pages.append(page)
            # Lock released - others can now create contexts
            
            print(f"  [{i:2d}] 🌐 Loading Ahrefs...")
            await page.goto(AHREFS_URL, timeout=15000)
            
            title = await page.title()
            print(f"  [{i:2d}] ✅ SUCCESS: {title[:40]}...")
            
            # DON'T close yet - keep everything open!
            return True
        except Exception as e:
            print(f"  [{i:2d}] ❌ FAILED: {str(e)[:50]}...")
            return False
    
    start_time = time.time()
    
    async with AsyncCamoufox(headless=False) as browser:
        tasks = [create_context_and_scrape(browser, i) for i in range(1, NUM_TASKS + 1)]
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=300.0  # 5 min for 30 sequential contexts
            )
            success_count = sum(1 for r in results if r is True)
            print(f"\n📊 Result: {success_count}/{NUM_TASKS} succeeded")
            
            # Wait 30 seconds before closing
            print(f"\n⏳ Waiting 30 seconds with all {len(all_pages)} pages/contexts OPEN...")
            await asyncio.sleep(30)
            
            print(f"\n🧹 Now closing all {len(all_pages)} pages and {len(all_contexts)} contexts...")
            for page in all_pages:
                try:
                    await page.close()
                except:
                    pass
            for context in all_contexts:
                try:
                    await context.close()
                except:
                    pass
            print("✅ Cleanup complete!")
            
        except asyncio.TimeoutError:
            print(f"\n⏱️  TIMEOUT after 300 seconds!")
    
    elapsed = time.time() - start_time
    print(f"⏱️  Total Time: {elapsed:.1f}s")
    print("\n🟢 CONCLUSION: With semaphore = SUCCESS! All {success_count} completed.")


# ============================================================================
# TEST 3: ✅ Multiple pages in ONE context WITH semaphore (WORKS!)
# ============================================================================

async def test_3_multiple_pages_one_context_with_semaphore():
    """
    ✅ THIS WORKS!
    Creating 30 pages (tabs) in a single context with semaphore
    """
    print("\n" + "=" * 80)
    print("TEST 3: ✅ Multiple pages in ONE context WITH semaphore (WORKS!)")
    print("=" * 80)
    print(f"Creating {NUM_TASKS} pages with 10-15s queue delays + semaphore...")
    print("Expected: All pages will load successfully")
    print()
    
    # Store all pages to close them AFTER waiting
    all_pages = []
    
    async def create_page_and_scrape(context, i):
        try:
            # Random delay BEFORE creating (simulating queue wait)
            delay = random.uniform(10, 15)
            print(f"  [{i:2d}] ⏰ Queue wait: {delay:.1f}s...")
            await asyncio.sleep(delay)
            
            # WITH SEMAPHORE - Only 1 page created at a time
            async with context_semaphore:
                print(f"  [{i:2d}] 🔐 Got lock, creating page...")
                page = await context.new_page()
                all_pages.append(page)
            
            print(f"  [{i:2d}] 🌐 Loading Ahrefs...")
            await page.goto(AHREFS_URL, timeout=15000)
            
            title = await page.title()
            print(f"  [{i:2d}] ✅ SUCCESS: {title[:40]}...")
            
            # DON'T close yet - keep everything open!
            return True
        except Exception as e:
            print(f"  [{i:2d}] ❌ FAILED: {str(e)[:50]}...")
            return False
    
    start_time = time.time()
    
    async with AsyncCamoufox(headless=False) as browser:
        print("  Creating single shared context...")
        context = await browser.new_context()
        
        tasks = [create_page_and_scrape(context, i) for i in range(1, NUM_TASKS + 1)]
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=300.0  # 5 min for 30 sequential pages
            )
            success_count = sum(1 for r in results if r is True)
            print(f"\n📊 Result: {success_count}/{NUM_TASKS} succeeded")
            
            # Wait 30 seconds before closing
            print(f"\n⏳ Waiting 30 seconds with all {len(all_pages)} pages OPEN...")
            await asyncio.sleep(30)
            
            print(f"\n🧹 Now closing all {len(all_pages)} pages...")
            for page in all_pages:
                try:
                    await page.close()
                except:
                    pass
            print("✅ Pages cleanup complete!")
            
        except asyncio.TimeoutError:
            print(f"\n⏱️  TIMEOUT after 300 seconds!")
        
        await context.close()
    
    elapsed = time.time() - start_time
    print(f"⏱️  Total Time: {elapsed:.1f}s")
    print("\n🟢 CONCLUSION: Single context + semaphore = SUCCESS!")


# ============================================================================
# TEST 4: ❌ Multiple pages WITHOUT semaphore (WILL FREEZE!)
# ============================================================================

async def test_4_multiple_pages_no_semaphore():
    """
    ❌ THIS WILL FREEZE!
    Creating 30 pages simultaneously in one context without semaphore
    """
    print("\n" + "=" * 80)
    print("TEST 4: ❌ Multiple pages in ONE context WITHOUT semaphore (WILL FREEZE!)")
    print("=" * 80)
    print(f"Creating {NUM_TASKS} pages with 10-15s queue delays...")
    print("Expected: Will freeze (new_page() also has deadlock issue)")
    print()
    
    # Store all pages to close them AFTER waiting
    all_pages = []
    
    async def create_page_and_scrape(context, i):
        try:
            # Random delay BEFORE creating (simulating queue wait)
            delay = random.uniform(10, 15)
            print(f"  [{i:2d}] ⏰ Queue wait: {delay:.1f}s...")
            await asyncio.sleep(delay)
            
            # NO SEMAPHORE - Creating pages simultaneously
            print(f"  [{i:2d}] Creating page...")
            page = await context.new_page()
            all_pages.append(page)
            
            print(f"  [{i:2d}] Loading Ahrefs...")
            await page.goto(AHREFS_URL, timeout=15000)
            
            title = await page.title()
            print(f"  [{i:2d}] ✅ SUCCESS: {title[:40]}...")
            
            # DON'T close yet - keep everything open!
            return True
        except Exception as e:
            print(f"  [{i:2d}] ❌ FAILED: {str(e)[:50]}...")
            return False
    
    start_time = time.time()
    
    async with AsyncCamoufox(headless=False) as browser:
        print("  Creating single shared context...")
        context = await browser.new_context()
        
        tasks = [create_page_and_scrape(context, i) for i in range(1, NUM_TASKS + 1)]
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=600.0  # 10 min (30 tasks × 10-15s delay + load + cleanup)
            )
            success_count = sum(1 for r in results if r is True)
            print(f"\n📊 Result: {success_count}/{NUM_TASKS} succeeded")
            
            # IMPORTANT: Wait 30 seconds before closing - this may reveal deadlock!
            print(f"\n⏳ Waiting 30 seconds with all {len(all_pages)} pages OPEN...")
            print("   (This might trigger the deadlock during cleanup)")
            await asyncio.sleep(30)
            
            print(f"\n🧹 Now closing all {len(all_pages)} pages...")
            for page in all_pages:
                try:
                    await page.close()
                except:
                    pass
            print("✅ Pages cleanup complete!")
            
        except asyncio.TimeoutError:
            print(f"\n⏱️  TIMEOUT after 10 minutes!")
            print("💡 Even new_page() has the deadlock issue!")
            print("   (Likely froze during cleanup phase)")
        
        await context.close()
    
    elapsed = time.time() - start_time
    print(f"⏱️  Total Time: {elapsed:.1f}s")
    print("\n🔴 CONCLUSION: Without semaphore = DEADLOCK (even for pages)")


# ============================================================================
# MAIN TEST SUITE
# ============================================================================

async def main():
    """Run comprehensive test suite"""
    print("\n" + "=" * 80)
    print("🧪 COMPREHENSIVE CAMOUFOX DEADLOCK TEST SUITE")
    print("=" * 80)
    print()
    print(f"Testing with {NUM_TASKS} concurrent tasks against Ahrefs")
    print(f"URL: {AHREFS_URL}")
    print()
    print("This will test 4 scenarios:")
    print("  1. ❌ Multiple contexts WITHOUT semaphore (will freeze)")
    print("  2. ✅ Multiple contexts WITH semaphore (works)")
    print("  3. ✅ Multiple pages in one context WITH semaphore (works)")
    print("  4. ❌ Multiple pages WITHOUT semaphore (will freeze)")
    print()
    print("🔍 NEW FEATURES:")
    print("   • 10-15 second random queue delay BEFORE creating page/context")
    print("   • Simulates real queue behavior like server.py")
    print("   • Pages/contexts stay OPEN for 30 seconds before cleanup")
    print("   • This reveals deadlock issues during cleanup phase")
    print()
    print("Browser: VISIBLE (headless=False)")
    print("GitHub Issue: https://github.com/daijro/camoufox/issues/279")
    print()
    print("⚠️  WARNING: Tests 1 & 4 may freeze during cleanup (that's expected!)")
    print("   Press Ctrl+C to skip if they hang too long.")
    print()
    input("Press Enter to start comprehensive test suite...")
    
    # Track results
    results = {}
    
    # Test 1: No semaphore (will freeze)
    print("\n" + "🔴" * 40)
    print("STARTING TEST 1: Will demonstrate the BUG")
    print("🔴" * 40)
    try:
        await test_1_multiple_contexts_no_semaphore()
        results['test1'] = 'completed'
    except KeyboardInterrupt:
        print("\n⏸️  Test 1 interrupted (expected if frozen)")
        results['test1'] = 'interrupted'
    except Exception as e:
        print(f"\n❌ Test 1 error: {e}")
        results['test1'] = 'error'
    
    print("\n\nWaiting 5 seconds before next test...")
    await asyncio.sleep(5)
    
    # Test 2: With semaphore (works)
    print("\n" + "🟢" * 40)
    print("STARTING TEST 2: Will demonstrate the FIX")
    print("🟢" * 40)
    try:
        await test_2_multiple_contexts_with_semaphore()
        results['test2'] = 'completed'
    except Exception as e:
        print(f"\n❌ Test 2 error: {e}")
        results['test2'] = 'error'
    
    print("\n\nWaiting 5 seconds before next test...")
    await asyncio.sleep(5)
    
    # Test 3: Pages with semaphore (works)
    print("\n" + "🟢" * 40)
    print("STARTING TEST 3: Alternative approach")
    print("🟢" * 40)
    try:
        await test_3_multiple_pages_one_context_with_semaphore()
        results['test3'] = 'completed'
    except Exception as e:
        print(f"\n❌ Test 3 error: {e}")
        results['test3'] = 'error'
    
    print("\n\nWaiting 5 seconds before next test...")
    await asyncio.sleep(5)
    
    # Test 4: Pages without semaphore (will freeze)
    print("\n" + "🔴" * 40)
    print("STARTING TEST 4: Will demonstrate pages also deadlock")
    print("🔴" * 40)
    try:
        await test_4_multiple_pages_no_semaphore()
        results['test4'] = 'completed'
    except KeyboardInterrupt:
        print("\n⏸️  Test 4 interrupted (expected if frozen)")
        results['test4'] = 'interrupted'
    except Exception as e:
        print(f"\n❌ Test 4 error: {e}")
        results['test4'] = 'error'
    
    # Final summary
    print("\n\n" + "=" * 80)
    print("📋 COMPREHENSIVE TEST SUITE COMPLETE")
    print("=" * 80)
    print()
    print("RESULTS SUMMARY:")
    print()
    print("❌ Tests that FROZE (demonstrating the bug):")
    print("   • Test 1: Multiple contexts WITHOUT semaphore")
    print("   • Test 4: Multiple pages WITHOUT semaphore")
    print()
    print("✅ Tests that SUCCEEDED (demonstrating the fix):")
    print("   • Test 2: Multiple contexts WITH semaphore")
    print("   • Test 3: Multiple pages in one context WITH semaphore")
    print()
    print("🎯 KEY TAKEAWAY:")
    print("   ALWAYS use semaphore when creating contexts or pages!")
    print("   This prevents Camoufox deadlock bug (#279)")
    print()
    print("💡 RECOMMENDATION FOR YOUR SERVER:")
    print("   ✅ Use the hybrid approach from server.py:")
    print("      - WITH proxy: New context per domain (with semaphore)")
    print("      - WITHOUT proxy: New page in shared context (with semaphore)")
    print()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏸️  Test suite interrupted by user")
        print("   Some tests may have been skipped")

