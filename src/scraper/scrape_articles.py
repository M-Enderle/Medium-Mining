"""
Synchronous Medium scraper using Playwright.
Visits Medium articles, extracts metadata, and takes screenshots.
"""

import logging
import random
import signal
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread

from playwright.sync_api import sync_playwright
from sqlalchemy.orm import Session

from database.database import SessionLocal
from scraper.medium_helpers import (extract_metadata_and_comments,
                                    fetch_random_urls, persist_article_data,
                                    update_url_status)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("article_scraper.log"), logging.StreamHandler()],
)

SCREENSHOT_DIR = Path("./screenshots").mkdir(exist_ok=True, parents=True) or Path(
    "./screenshots"
)
MAX_CONCURRENT = 1
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


def process_article(
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
        # Use mobile viewport and user agent from the beginning
        context = browser.new_context(
            viewport={"width": 390, "height": 844},  # iPhone 12 dimensions
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
            locale=random.choice(["en-US", "en-GB"]),
            device_scale_factor=2.0,  # Retina display simulation
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
        )

        logging.info(f"Using mobile viewport for processing URL: {url}")

        page = context.new_page()
        try:
            # Only log critical information to reduce output noise
            logging.debug(f"Processing: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.mouse.wheel(0, random.randint(100, 300))

            # Extract and save article data, including comments
            metadata = extract_metadata_and_comments(page)

            # Additional logging for comments count
            comment_count = metadata.get("comments_count", 0)
            logging.info(
                f"Article '{metadata.get('title', 'Unknown')[:50]}...' has {comment_count} comments"
            )

            persist_article_data(session, url_id, metadata)

            filename = f"{worker_idx}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            page.screenshot(path=str(SCREENSHOT_DIR / filename), full_page=True)
            success = True

            # Update performance metrics silently
            update_metrics()
        finally:
            page.close()
            context.close()
    except Exception as e:
        logging.error(f"Error on {url}: {e}")

    if not shutdown_event.is_set():
        update_url_status(session, url_id, success)


def get_random_urls(session, count=100):
    """Get random unprocessed URLs synchronously"""
    try:
        # Using the renamed function
        return fetch_random_urls(session, count)
    except Exception as e:
        logging.error(f"Failed to get URLs: {e}")
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
                process_article(url_data, browser, index, session)
                task_queue.task_done()
            except Exception as e:
                if not shutdown_event.is_set():
                    logging.error(f"Worker thread error: {e}")

        try:
            browser.close()
        except Exception as e:
            pass


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

        logging.info(f"=== FINAL PERFORMANCE SUMMARY ===")
        logging.info(f"Total processed: {completed_tasks} articles")
        logging.info(f"Average speed: {speed:.2f} articles/minute")
        logging.info(f"Total time: {elapsed_time/60:.1f} minutes")
        if elapsed_time > 0 and speed > 0:
            logging.info(f"Processing time per article: {60/speed:.2f} seconds")


def handle_signal(signum, frame):
    """Signal handler for graceful shutdown"""
    logging.warning(f"Received signal {signum}, initiating shutdown...")
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
            # Use synchronous function to get URLsw
            # url_data = get_random_urls(session, count=10)
            url_data = [
                (
                    1,
                    "https://medium.com/@harendra21/how-i-am-using-a-lifetime-100-free-server-bd241e3a347a",
                )
            ]
            logging.info(
                f"Starting to process {len(url_data)} URLs with {MAX_CONCURRENT} workers"
            )

            # Create a task queue
            task_queue = Queue()

            # Browser factory function
            def create_browser(playwright):
                return playwright.chromium.launch(
                    headless=False,
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
                logging.warning("Shutting down gracefully...")
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
        logging.error(f"Unhandled error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
