"""
Asynchronous Medium scraper using Playwright.
Visits Medium articles, extracts metadata, and takes screenshots.
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import Browser, async_playwright
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import AsyncSessionLocal
from scraper.medium_helpers import (extract_metadata, get_random_urls,
                                    save_article, setup_signal_handlers,
                                    update_url_status)

logger = logging.getLogger(__name__)
SCREENSHOT_DIR = Path("./screenshots").mkdir(exist_ok=True, parents=True) or Path(
    "./screenshots"
)
MAX_CONCURRENT, shutdown_event = 10, asyncio.Event()

# Track performance metrics
completed_tasks = 0
start_time = 0
metrics_lock = asyncio.Lock()

async def update_metrics():
    """Update metrics counter without displaying intermediate results."""
    global completed_tasks
    async with metrics_lock:
        completed_tasks += 1
        # No intermediate logging here


async def take_screenshot(
    url_data,
    browser: Browser,
    semaphore: asyncio.Semaphore,
    index: int,
    session: AsyncSession,
):
    """
    Process a Medium article: extract metadata, save to database, and take screenshot.

    Args:
        url_data: Tuple of (url_id, url)
        browser: Playwright browser instance
        semaphore: Concurrency limiter
        index: Task index for filename
        session: Database session
    """
    if shutdown_event.is_set():
        return
    url_id, url = url_data
    success = False

    async with semaphore:
        try:
            context = await browser.new_context(
                viewport={
                    "width": random.randint(1024, 1280),
                    "height": random.randint(768, 900),
                },
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                locale=random.choice(["en-US", "en-GB"]),
            )
            await context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
            )

            page = await context.new_page()
            try:
                # Only log critical information to reduce output noise
                logger.debug(f"Processing: {url}")  # Changed to debug level
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.mouse.wheel(0, random.randint(100, 300))

                # Extract and save article data, take screenshot
                await save_article(session, url_id, await extract_metadata(page))
                filename = f"{index}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / filename), full_page=True
                )
                success = True
                
                # Update performance metrics silently
                await update_metrics()
            finally:
                await page.close()
                await context.close()
        except Exception as e:
            logger.error(f"Error on {url}: {e}")

        if not shutdown_event.is_set():
            await update_url_status(session, url_id, success)


async def main():
    """
    Main execution function. Sets up browser, creates tasks, and manages execution.
    Handles graceful shutdown on interruption.
    """
    browser, tasks = None, []
    setup_signal_handlers(shutdown_event)
    
    # Initialize performance tracking
    global start_time, completed_tasks
    start_time = time.time()
    completed_tasks = 0

    try:
        async with AsyncSessionLocal() as session:
            url_data = await get_random_urls(session, count=100)
            logger.info(
                f"Starting to process {len(url_data)} URLs with {MAX_CONCURRENT} workers"
            )

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )

                semaphore = asyncio.Semaphore(MAX_CONCURRENT)
                tasks = [
                    asyncio.create_task(
                        take_screenshot(url, browser, semaphore, i, session)
                    )
                    for i, url in enumerate(url_data)
                ]
                
                # Schedule final metrics display only
                metrics_task = asyncio.create_task(quiet_metrics_monitor())
                tasks.append(metrics_task)
                
                # Wait for completion or shutdown
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=(
                        asyncio.ALL_COMPLETED
                        if not shutdown_event.is_set()
                        else asyncio.FIRST_COMPLETED
                    ),
                )

                if shutdown_event.is_set():
                    logger.warning("Shutting down gracefully...")
                    for task in pending:
                        task.cancel()

                if browser:
                    await browser.close()

    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        if browser:
            await browser.close()
            
    # Display only final metrics
    await display_final_metrics()


async def quiet_metrics_monitor():
    """Monitor metrics without intermediate output."""
    while not shutdown_event.is_set():
        await asyncio.sleep(60)  # Check every minute but don't produce output
        
        # No intermediate reporting here
        

async def display_final_metrics():
    """Display final performance metrics."""
    global completed_tasks, start_time
    
    elapsed_time = time.time() - start_time
    if completed_tasks > 0 and elapsed_time > 0:
        speed = completed_tasks / (elapsed_time / 60)
        
        logger.info(f"=== FINAL PERFORMANCE SUMMARY ===")
        logger.info(f"Total processed: {completed_tasks} articles")
        logger.info(f"Average speed: {speed:.2f} articles/minute")
        logger.info(f"Total time: {elapsed_time/60:.1f} minutes")
        if elapsed_time > 0 and speed > 0:
            logger.info(f"Processing time per article: {60/speed:.2f} seconds")


if __name__ == "__main__":
    # Configure logging to reduce verbosity
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    # Set other loggers to WARNING level to reduce noise
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    asyncio.run(main())
