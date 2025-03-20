import asyncio, random
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from playwright.async_api import async_playwright, Browser
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import AsyncSessionLocal
from scraper.medium_helpers import (
    get_random_urls, update_url_status, extract_metadata, 
    save_article, setup_signal_handlers
)

# Setup constants and state
SCREENSHOT_DIR = Path("./screenshots").mkdir(exist_ok=True, parents=True) or Path("./screenshots")
MAX_CONCURRENT = 10
shutdown_event = asyncio.Event()

async def take_screenshot(url_data: Tuple[int, str], browser: Browser, semaphore: asyncio.Semaphore, 
                         index: int, session: AsyncSession):
    if shutdown_event.is_set(): return
    url_id, url = url_data
    success = False
    
    async with semaphore:
        try:
            context = await browser.new_context(
                viewport={"width": random.randint(1024, 1280), "height": random.randint(768, 900)},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                locale=random.choice(["en-US", "en-GB"])
            )
            await context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});")
            
            page = await context.new_page()
            try:
                if shutdown_event.is_set(): return
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.mouse.wheel(0, random.randint(100, 300))
                
                # Extract article metadata
                article_metadata = await extract_metadata(page)
                await save_article(session, url_id, article_metadata)
                
                # Take screenshot
                filename = f"{index}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                await page.screenshot(path=str(SCREENSHOT_DIR / filename), full_page=True)
                print(f"Screenshot: {filename}")
                success = True
            finally:
                await page.close()
                await context.close()
        except Exception as e:
            print(f"Error on {url}: {e}")
        
        if not shutdown_event.is_set():
            await update_url_status(session, url_id, success)

async def main():
    browser, tasks = None, []
    
    # Set up signal handlers
    setup_signal_handlers(shutdown_event)
    
    try:
        async with AsyncSessionLocal() as session:
            url_data = await get_random_urls(session, count=100)
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True, 
                    args=["--disable-blink-features=AutomationControlled"]
                )
                
                semaphore = asyncio.Semaphore(MAX_CONCURRENT)
                tasks = [asyncio.create_task(take_screenshot(url, browser, semaphore, i, session)) 
                        for i, url in enumerate(url_data)]
                
                # Wait for completion or shutdown signal
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.ALL_COMPLETED if not shutdown_event.is_set() 
                    else asyncio.FIRST_COMPLETED
                )
                
                # Clean up on shutdown
                if shutdown_event.is_set():
                    print("\nShutting down gracefully...")
                    for task in pending:
                        task.cancel()
                
                # Close browser safely
                if browser:
                    try:
                        await browser.close()
                    except Exception as e:
                        print(f"Error closing browser: {e}")
                
    except Exception as e:
        print(f"Error: {e}")
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
