#!/usr/bin/env python3
"""
Camoufox Browser Management Helper

Handles:
- Browser initialization
- Context pooling (Test 4 approach)
- Page creation in shared contexts
"""

import asyncio
from camoufox import AsyncCamoufox
from browserforge.fingerprints import Screen

# Global browser instance
global_browser = None
browser_lock = asyncio.Lock()

# Test 4 approach: Shared contexts (one per unique proxy + one for non-proxy)
shared_context_no_proxy = None  # For non-proxy requests
shared_contexts_with_proxy = {}  # Dict: proxy_key -> context (for proxy requests)
context_pool_lock = asyncio.Lock()

# Semaphores to serialize context/page creation (prevents Camoufox deadlock - issue #279)
context_creation_semaphore = asyncio.Semaphore(1)
page_creation_semaphore = asyncio.Semaphore(1)


async def initialize_browser():
    """Initialize the global browser instance"""
    global global_browser
    
    if global_browser is None:
        print("🚀 Initializing Camoufox browser instance...")
        global_browser = await AsyncCamoufox(
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
        ).__aenter__()
        print("✅ Browser instance ready!")
    
    return global_browser


async def close_browser():
    """Close all shared contexts and global browser instance"""
    global global_browser, shared_context_no_proxy, shared_contexts_with_proxy
    
    # Close non-proxy shared context
    if shared_context_no_proxy is not None:
        print("🔒 Closing non-proxy shared context...")
        await shared_context_no_proxy.close()
        shared_context_no_proxy = None
        print("✅ Non-proxy context closed!")
    
    # Close all proxy shared contexts
    if shared_contexts_with_proxy:
        print(f"🔒 Closing {len(shared_contexts_with_proxy)} proxy contexts...")
        for proxy_key, context in shared_contexts_with_proxy.items():
            await context.close()
            print(f"   ✅ Closed context for proxy: {proxy_key}")
        shared_contexts_with_proxy.clear()
        print("✅ All proxy contexts closed!")
    
    # Then close browser
    if global_browser is not None:
        print("🔒 Closing browser instance...")
        await global_browser.__aexit__(None, None, None)
        global_browser = None
        print("✅ Browser closed!")


async def get_or_create_context(proxy=None):
    """
    Get or create a shared context (Test 4 approach)
    
    Args:
        proxy: Dict with keys: server, username, password (optional)
    
    Returns:
        context: The shared context to use
    """
    global global_browser, shared_context_no_proxy, shared_contexts_with_proxy
    
    # Ensure browser is initialized
    if global_browser is None:
        await initialize_browser()
    
    if proxy:
        # WITH PROXY: Get or create shared context for this specific proxy
        proxy_key = f"{proxy['server']}"  # Unique key per proxy
        
        async with context_pool_lock:
            if proxy_key not in shared_contexts_with_proxy:
                print(f"🆕 Creating shared context for proxy: {proxy_key}")
                # SERIALIZE context creation (Camoufox issue #279)
                async with context_creation_semaphore:
                    shared_contexts_with_proxy[proxy_key] = await global_browser.new_context(proxy=proxy)
                print(f"✅ Proxy context created! (Total contexts: {len(shared_contexts_with_proxy) + 1})")
            
            context = shared_contexts_with_proxy[proxy_key]
        
        print(f"♻️  Reusing shared context for proxy: {proxy_key}")
    else:
        # WITHOUT PROXY: Use shared non-proxy context
        async with context_pool_lock:
            if shared_context_no_proxy is None:
                print(f"🆕 Creating shared context for non-proxy requests...")
                # SERIALIZE context creation (Camoufox issue #279)
                async with context_creation_semaphore:
                    shared_context_no_proxy = await global_browser.new_context()
                print(f"✅ Non-proxy context created!")
            
            context = shared_context_no_proxy
        
        print(f"♻️  Reusing shared non-proxy context")
    
    return context


async def create_page_in_context(context, domain):
    """
    Create a new page in the given context (SERIALIZED to prevent Camoufox deadlock)
    
    Args:
        context: The browser context to create the page in
        domain: Domain name (for logging)
    
    Returns:
        page: The created page
    """
    # SERIALIZE page creation (Camoufox issue #279)
    async with page_creation_semaphore:
        page = await context.new_page()
        print(f"📄 New page created for {domain} (serialized)")
    return page


def get_context_pool_stats():
    """Get statistics about the context pool"""
    return {
        'no_proxy_context': 'created' if shared_context_no_proxy else 'not created',
        'proxy_contexts': len(shared_contexts_with_proxy),
        'total_contexts': (1 if shared_context_no_proxy else 0) + len(shared_contexts_with_proxy)
    }

