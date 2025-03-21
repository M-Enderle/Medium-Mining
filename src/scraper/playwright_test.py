"""
Synchronous Medium scraper using Playwright.
Visits Medium articles, extracts metadata, and takes screenshots.
"""

import logging
import random
import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread

from playwright.sync_api import sync_playwright
from sqlalchemy.orm import Session

from database.database import SessionLocal
from scraper.medium_helpers import extract_metadata, save_article, setup_signal_handlers

logger = logging.getLogger(__name__)
SCREENSHOT_DIR = Path("./screenshots").mkdir(exist_ok=True, parents=True) or Path(
    "./screenshots"
)
MAX_CONCURRENT = 10
shutdown_event = Event()

# Track performance metrics
completed_tasks = 0
start_time = 0
metrics_lock = Lock()


def update_metrics():
    """Update metrics counter without displaying intermediate results."""
    global completed_tasks
    with metrics_lock:
        completed_tasks += 1


def take_screenshot(
    url_data,
    browser,
    worker_idx: int,
    session: Session,
):
    """
    Process a Medium article: extract metadata, save to database, and take screenshot.

    Args:
        url_data: Tuple of (url_id, url)
        browser: Playwright browser instance
        worker_idx: Worker index for filename
        session: Database session
    """
    if shutdown_event.is_set():
        return

    url_id, url = url_data
    success = False

    try:
        context = browser.new_context(
            viewport={
                "width": random.randint(1024, 1280),
                "height": random.randint(768, 900),
            },
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            locale=random.choice(["en-US", "en-GB"]),
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
        )

        page = context.new_page()
        try:
            # Only log critical information to reduce output noise
            logger.debug(f"Processing: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.mouse.wheel(0, random.randint(100, 300))

            # Extract and save article data, take screenshot
            metadata = extract_metadata(page)
            save_article(session, url_id, metadata)

            filename = f"{worker_idx}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            page.screenshot(path=str(SCREENSHOT_DIR / filename), full_page=True)
            success = True

            # Update performance metrics silently
            update_metrics()
        finally:
            page.close()
            context.close()
    except Exception as e:
        logger.error(f"Error on {url}: {e}")

    if not shutdown_event.is_set():
        update_url_status(session, url_id, success)


def update_url_status(session, url_id, success):
    """Update URL processing status synchronously"""
    from database.database import URL

    try:
        url = session.query(URL).filter(URL.id == url_id).first()
        if url:
            # Update status or other fields as needed
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update URL status: {e}")


def get_random_urls(session, count=100):
    """Get random unprocessed URLs synchronously"""
    from database.database import URL

    try:
        # Synchronous query to get URLs
        urls = session.query(URL.id, URL.url).limit(count).all()
        return urls
    except Exception as e:
        logger.error(f"Failed to get URLs: {e}")
        return []


def worker_thread(task_queue, browser_factory, session):
    """Worker thread function to process URLs"""
    # Each thread creates its own browser instance
    with sync_playwright() as p:
        browser = browser_factory(p)
        while not shutdown_event.is_set():
            try:
                task = task_queue.get(timeout=1)
                if task is None:  # Sentinel value to stop thread
                    break

                url_data, index = task
                take_screenshot(url_data, browser, index, session)
                task_queue.task_done()
            except Exception as e:
                if not shutdown_event.is_set():
                    logger.error(f"Worker thread error: {e}")

        browser.close()


def quiet_metrics_monitor(stop_event):
    """Monitor metrics without intermediate output."""
    while not stop_event.is_set():
        time.sleep(60)  # Check every minute but don't produce output


def display_final_metrics():
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


def handle_signal(signum, frame):
    """Signal handler for graceful shutdown"""
    logger.warning(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


def main():
    """
    Main execution function. Sets up browser, creates threads, and manages execution.
    Handles graceful shutdown on interruption.
    """
    # Initialize performance tracking
    global start_time, completed_tasks
    start_time = time.time()
    completed_tasks = 0

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    threads = []
    metrics_thread = None

    try:
        # Create synchronous session
        session = SessionLocal()
        try:
            # Use synchronous function to get URLs
            url_data = get_random_urls(session, count=100)
            logger.info(
                f"Starting to process {len(url_data)} URLs with {MAX_CONCURRENT} workers"
            )

            # Create a task queue
            task_queue = Queue()

            # Browser factory function
            def create_browser(playwright):
                return playwright.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )

            # Start worker threads
            for i in range(MAX_CONCURRENT):
                thread = Thread(
                    target=worker_thread,
                    args=(task_queue, create_browser, session),
                    daemon=True,
                )
                thread.start()
                threads.append(thread)

            # Add metrics monitor thread
            metrics_stop = Event()
            metrics_thread = Thread(
                target=quiet_metrics_monitor, args=(metrics_stop,), daemon=True
            )
            metrics_thread.start()

            # Add tasks to the queue
            for i, url in enumerate(url_data):
                task_queue.put((url, i))

            # Add sentinel values to stop workers
            for _ in range(MAX_CONCURRENT):
                task_queue.put(None)

            # Wait for tasks to complete or shutdown
            while not task_queue.empty() and not shutdown_event.is_set():
                time.sleep(1)

            # Wait for completion or shutdown
            if shutdown_event.is_set():
                logger.warning("Shutting down gracefully...")
                # Don't need to cancel threads as they check shutdown_event

            # Wait for threads to finish (with timeout)
            for thread in threads:
                thread.join(timeout=5)

            # Stop metrics thread
            metrics_stop.set()
            if metrics_thread:
                metrics_thread.join(timeout=2)

        finally:
            # Display final metrics
            display_final_metrics()
            # Ensure session is closed
            session.close()

    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)


if __name__ == "__main__":
    # Configure logging to reduce verbosity
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    # Set other loggers to WARNING level to reduce noise
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    main()
