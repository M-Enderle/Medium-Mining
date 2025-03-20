import asyncio, random, os, signal
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from playwright.async_api import async_playwright, Browser
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import URL, AsyncSessionLocal

# Setup constants and state
SCREENSHOT_DIR = Path("./screenshots").mkdir(exist_ok=True, parents=True) or Path("./screenshots")
MAX_CONCURRENT = 10
db_lock, shutdown_event = asyncio.Lock(), asyncio.Event()

async def get_random_urls(session: AsyncSession, count: int = 10) -> List[Tuple[int, str]]:
    result = await session.execute(select(URL.id, URL.url).order_by(func.random()).limit(count))
    return [(row[0], row[1]) for row in result]

async def update_url_status(session: AsyncSession, url_id: int, success: bool):
    async with db_lock:
        try:
            await session.execute(update(URL).where(URL.id == url_id)
                                .values(last_crawled=datetime.now(), 
                                        crawl_status="Successful" if success else "Failed"))
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"DB error for {url_id}: {e}")

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
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_event.set())
    
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
                    tasks, return_when=asyncio.FIRST_COMPLETED if shutdown_event.is_set() 
                    else asyncio.ALL_COMPLETED
                )
                
                # Clean up on shutdown
                if shutdown_event.is_set():
                    print("\nShutting down gracefully...")
                    for task in pending:
                        task.cancel()
                
                # Close browser safely - no need to check if it's closed
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
                pass  # Browser might already be closed

if __name__ == "__main__":
    asyncio.run(main())
