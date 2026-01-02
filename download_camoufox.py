"""
Pre-download Camoufox browser package during Docker build time.
This script initializes Camoufox which triggers the browser download and caching.
"""
from __future__ import annotations
import asyncio
from camoufox.async_api import AsyncCamoufox


async def download_browser():
    """Initialize Camoufox to download and cache the browser package."""
    print("Downloading Camoufox browser package...")
    async with AsyncCamoufox(headless=True, os='linux'):
        print("Browser downloaded and cached successfully")


if __name__ == '__main__':
    asyncio.run(download_browser())

