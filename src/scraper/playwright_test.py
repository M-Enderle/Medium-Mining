"""
Asynchronous Medium scraper using Playwright.
Visits Medium articles, extracts metadata, and takes screenshots.
"""

import asyncio
import logging
import random
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
                logger.info(f"Processing: {url}")
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.mouse.wheel(0, random.randint(100, 300))

                # Extract and save article data, take screenshot
                await save_article(session, url_id, await extract_metadata(page))
                filename = f"{index}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / filename), full_page=True
                )
                success = True
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

    try:
        async with AsyncSessionLocal() as session:
            url_data = await get_random_urls(session, count=100)
            logger.info(
                f"Processing {len(url_data)} URLs with {MAX_CONCURRENT} workers"
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    asyncio.run(main())
