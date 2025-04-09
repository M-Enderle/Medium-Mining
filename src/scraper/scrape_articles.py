import logging
import random
import time
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, Optional

from playwright.sync_api import Browser, BrowserContext, sync_playwright
from sqlalchemy.orm import Session

from database.database import SessionLocal
from scraper.medium_helpers import (fetch_random_urls, persist_article_data,
                                    setup_signal_handlers, update_url_status,
                                    verify_its_an_article)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("article_scraper.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Global state variables
shutdown_event = Event()
completed_tasks = 0
start_time = 0
metrics_lock = Lock()


def update_metrics() -> None:
    """
    Update the metrics for completed tasks.
    """
    global completed_tasks
    with metrics_lock:
        completed_tasks += 1


def display_final_metrics() -> None:
    """
    Display the final metrics after processing.
    """
    global completed_tasks, start_time
    elapsed_time = time.time() - start_time

    if elapsed_time > 0:
        speed = completed_tasks / (elapsed_time / 60)
    else:
        speed = 0

    logger.info("=== FINAL PERFORMANCE SUMMARY ===")
    logger.info(f"Total processed: {completed_tasks} articles")
    logger.info(f"Average speed: {speed:.2f} articles/minute")
    logger.info(f"Total time: {elapsed_time/60:.1f} minutes")

    if speed > 0:
        logger.info(f"Processing time per article: {60/speed:.2f} seconds")


def create_browser(playwright, headless: bool) -> Browser:
    """
    Create a Playwright browser instance.
    Args:
        playwright: The Playwright instance.
        headless (bool): Whether to run in headless mode.
    Returns:
        Browser: The Playwright browser instance
    """
    return playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )


def get_context(browser: Browser) -> BrowserContext:
    """
    Randomize the user agent for the browser context.
    Args:
        browser (Browser): The Playwright browser instance.
    Returns:
        BrowserContext: The browser context with a randomized user agent.
    """
    context = browser.new_context(
        viewport=random.choice(
            [
                {"width": 390, "height": 844},  # iPhone 12 dimensions
                {"width": 375, "height": 667},  # iPhone SE dimensions
                {"width": 414, "height": 896},  # iPhone 11 Pro Max dimensions
                {"width": 360, "height": 640},  # Samsung Galaxy S8 dimensions
                {"width": 412, "height": 915},  # Google Pixel 5 dimensions
            ]
        ),
        user_agent=random.choice(
            [
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",  # iPhone 12
                "Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1",  # iPhone SE
                "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1",  # iPhone 11 Pro Max
                "Mozilla/5.0 (Linux; Android 8.0.0; SM-G950F Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.111 Mobile Safari/537.36",  # Samsung Galaxy S8
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",  # Google Pixel 5
            ]
        ),
        locale=random.choice(
            [
                "en-US",
                "en-GB",
                "fr-FR",
                "de-DE",
                "es-ES",
                "it-IT",
                "pt-PT",
                "ja-JP",
                "zh-CN",
            ]
        ),
        device_scale_factor=random.choice([1, 2]),
    )

    # Mask automation
    context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
    )

    return context


def random_mouse_movement(page: Any) -> None:
    """
    Simulate random mouse movements and scrolling.
    Args:
        page (Any): The Playwright page instance.
    """
    time.sleep(random.uniform(0.5, 1.5))
    page.mouse.move(
        random.randint(0, 300), random.randint(0, 300), steps=random.randint(10, 20)
    )
    page.mouse.wheel(0, random.randint(100, 300))
    time.sleep(random.uniform(0.3, 0.8))


def process_article(
    url_data: tuple[int, str], browser: Browser, worker_idx: int, session: Session
) -> None:
    """
    Process a single article URL.
    Args:
        url_data (tuple[int, str]): Tuple containing URL ID and URL.
        browser (Browser): The Playwright browser instance.
        worker_idx (int): Index of the worker thread.
        session (Session): SQLAlchemy session for database operations.
    """

    # stopping gracefully
    if shutdown_event.is_set():
        return

    url_id, url = url_data

    try:
        context = get_context(browser)

        with context.new_page() as page:
            logger.debug(f"Processing URL: {url}")
            page.goto(url, wait_until="load", timeout=20000)

            random_mouse_movement(page)

            if not verify_its_an_article(page):
                logger.info(f"URL is not an article: {url}")
                update_url_status(session, url_id, "not_article")
                return

            persist_article_data(session, url_id, page)

            update_url_status(session, url_id, "success")
            logger.info(f"Processed URL: {url}")

            update_metrics()

    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        update_url_status(session, url_id, "error", str(e))


def worker_thread(
    task_queue: Queue,
    browser_factory: callable,
    session_factory: callable,
    shutdown: Event,
) -> None:
    """
    Worker thread to process tasks from the queue.
    Args:
        task_queue (Queue): The queue containing tasks to process.
        browser_factory (callable): Function to create a browser instance.
        session_factory (callable): Function to create a session instance.
        shutdown (Event): Event to signal graceful shutdown.
    """
    while not shutdown.is_set():
        try:
            task = task_queue.get(timeout=1)
            if task is None:
                break

            url_data, worker_idx = task

            with sync_playwright() as p:
                browser = browser_factory(p)
                try:
                    with session_factory() as session:
                        process_article(url_data, browser, worker_idx, session)
                finally:
                    try:
                        browser.close()
                    except Exception as e:
                        logger.error(f"Error closing browser: {e}")

                task_queue.task_done()

        except Exception as e:
            if not shutdown.is_set():  # Only log if not shutting down
                logger.error(f"Worker thread error: {e}")


def main(
    headless: bool = True, workers: int = 5, url_count: Optional[int] = None
) -> None:
    """Main execution function for processing URLs with worker threads.

    Args:
        headless: Whether to run browser in headless mode
        workers: Number of worker threads
        url_count: Optional number of URLs to process
    """
    global start_time, shutdown_event

    # Set up signal handlers for graceful shutdown
    setup_signal_handlers(shutdown_event)

    start_time = time.time()
    task_queue = Queue()
    threads = []

    try:
        # Initialize database session factory
        session_factory = SessionLocal

        # Fetch URLs with proper session management
        with session_factory() as session:
            url_data = fetch_random_urls(session, url_count)

        logger.info(f"Starting to process {len(url_data)} URLs with {workers} workers")

        # Start worker threads
        for _ in range(workers):
            thread = Thread(
                target=worker_thread,
                args=(
                    task_queue,
                    lambda p: create_browser(p, headless),
                    session_factory,
                    shutdown_event,  # Pass the shutdown event to workers
                ),
                daemon=True,
            )
            threads.append(thread)
            thread.start()

        # Enqueue tasks and termination signals
        for i, url in enumerate(url_data):
            task_queue.put(((url[0], url[1]), i))
        for _ in range(workers):
            task_queue.put(None)

        # Monitor task completion
        while not task_queue.empty() and not shutdown_event.is_set():
            time.sleep(1)

        if shutdown_event.is_set():
            logger.warning("Shutting down gracefully...")

    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        raise

    finally:
        # Signal threads to stop if not already done
        if not shutdown_event.is_set():
            shutdown_event.set()

        # Cleanup threads
        for thread in threads:
            thread.join(timeout=5)
        display_final_metrics()


if __name__ == "__main__":
    main(headless=False, workers=2, url_count=100)
