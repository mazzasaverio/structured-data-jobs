"""Utility module for browser automation with Playwright."""
import logfire
import asyncio
from typing import Tuple, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext

async def setup_browser(
    headless: bool = True,
    width: int = 1280,
    height: int = 800,
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    timeout: int = 30000
) -> Tuple:
    """Set up Playwright browser and context with timeout protection.
    
    Args:
        headless (bool): Whether to run browser in headless mode
        width (int): Viewport width
        height (int): Viewport height
        user_agent (str): User agent string to use
        timeout (int): Timeout in milliseconds
        
    Returns:
        Tuple: (playwright, browser, context)
    """
    logfire.info("Setting up Playwright browser")
    
    # Add timeout protection for browser launch
    try:
        playwright = await asyncio.wait_for(
            async_playwright().start(),
            timeout=timeout/1000  # Convert ms to seconds
        )
        
        browser = await asyncio.wait_for(
            playwright.chromium.launch(headless=headless),
            timeout=timeout/1000
        )
        
        context = await asyncio.wait_for(
            browser.new_context(
                viewport={"width": width, "height": height},
                user_agent=user_agent
            ),
            timeout=timeout/1000
        )
        
        logfire.info("Playwright browser setup complete")
        return playwright, browser, context
    except asyncio.TimeoutError:
        logfire.error(f"Browser setup timed out after {timeout/1000} seconds")
        # Clean up any partial resources
        raise Exception("Browser setup timed out") 