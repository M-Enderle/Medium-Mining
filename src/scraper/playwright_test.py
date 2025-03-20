import asyncio
import os
import random
from datetime import datetime
from pathlib import Path
from typing import List

from playwright.async_api import async_playwright, Browser, Page
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Import from our database module
from database.database import URL, AsyncSessionLocal

# Directory to save screenshots
SCREENSHOT_DIR = Path("/Users/moritz/JKU/sem2/Medium-Mining/screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True, parents=True)

# Configure the maximum concurrent tasks
MAX_CONCURRENT = 15

async def get_random_urls(session: AsyncSession, count: int = 10) -> List[str]:
    """Fetch random URLs from the database."""
    stmt = select(URL.url).order_by(func.random()).limit(count)
    result = await session.execute(stmt)
    urls = [row[0] for row in result]
    return urls

async def take_screenshot(url: str, browser: Browser, semaphore: asyncio.Semaphore, index: int):
    """Open a page, take a screenshot, and save it."""
    async with semaphore:
        # Create a unique context for each page to avoid tracking
        context = await browser.new_context(
            viewport={"width": random.randint(1024, 1280), "height": random.randint(768, 900)},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            device_scale_factor=random.choice([1, 2]),
            locale=random.choice(["en-US", "en-GB", "en-CA"]),
            timezone_id="America/New_York",
            has_touch=random.choice([True, False])
        )
        
        # Randomize headers and behaviors
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)
        
        page = await context.new_page()
        
        try:
            # Randomize timing to appear more human-like
            await asyncio.sleep(random.uniform(1, 3))
            
            # Navigate with timeout and wait until network is idle
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Random scrolling behavior
            await page.mouse.wheel(0, random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Take the screenshot
            filename = f"{index}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            filepath = SCREENSHOT_DIR / filename
            await page.screenshot(path=str(filepath), full_page=True)
            print(f"Screenshot saved: {filepath}")
        except Exception as e:
            print(f"Error processing {url}: {e}")
        finally:
            await page.close()
            await context.close()

async def main():
    """Main function to run the scraping process."""
    # Get random URLs from database
    async with AsyncSessionLocal() as session:
        urls = await get_random_urls(session, count=100)
    
    # Create a semaphore to limit concurrent connections
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    async with async_playwright() as p:
        # Launch browser with stealth settings
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage"
            ]
        )
        
        # Process URLs with semaphore control
        tasks = [take_screenshot(url, browser, semaphore, i) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
