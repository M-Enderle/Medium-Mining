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
HEADLESS = False
shutdown_event = Event()
completed_tasks = 0
start_time = 0
metrics_lock = Lock()


def update_metrics():
    """Increment completed tasks counter."""
    global completed_tasks
    with metrics_lock:
        completed_tasks += 1


def process_article(url_data, browser, worker_idx: int, session: Session):
    """Process an article: extract, save, and screenshot."""
    if shutdown_event.is_set():
        return

    url_id, url = url_data
    success = False
    metadata = {}  # Initialize metadata

    try:
        context = browser.new_context(
            viewport={"width": 390, "height": 844},  # iPhone 12
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
            locale=random.choice(["en-US", "en-GB"]),
            device_scale_factor=2.0,
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
        )

        with context.new_page() as page:
            logging.debug(f"Processing URL: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.mouse.wheel(0, random.randint(100, 300))

            metadata = extract_metadata_and_comments(page)

            # Move persist_article_data inside the try block
            if persist_article_data(
                session, url_id, metadata
            ):  # Check the return value
                success = True

            filename = f"{worker_idx}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            page.screenshot(path=str(SCREENSHOT_DIR / filename), full_page=True)
            logging.debug(f"Saved screenshot to {filename}")

            update_metrics()  # Update metrics only on success

    except Exception as e:
        logging.error(f"Error on {url}: {e}")
    finally:
        update_url_status(session, url_id, success)


def worker_thread(task_queue, browser_factory, session_factory):
    """Worker thread to process URLs."""
    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=1)
            if task is None:
                break
            url_data, worker_idx = task
            with sync_playwright() as p:
                browser = browser_factory(p)
                try:
                    with session_factory() as session:  # Create a session for each task
                        process_article(url_data, browser, worker_idx, session)
                finally:
                    try:
                        browser.close()
                    except:
                        pass  # Ignore browser close errors
                task_queue.task_done()
        except Exception as e:
            if not shutdown_event.is_set():
                logging.error(f"Worker thread error: {e}")


def quiet_metrics_monitor(stop_event):
    """Monitor metrics without intermediate output."""
    while not stop_event.is_set():
        time.sleep(60)


def display_final_metrics():
    """Display final performance metrics."""
    global completed_tasks, start_time
    elapsed_time = time.time() - start_time
    speed = (
        completed_tasks / (elapsed_time / 60)
        if completed_tasks > 0 and elapsed_time > 0
        else 0
    )

    logging.info(f"=== FINAL PERFORMANCE SUMMARY ===")
    logging.info(f"Total processed: {completed_tasks} articles")
    logging.info(f"Average speed: {speed:.2f} articles/minute")
    logging.info(f"Total time: {elapsed_time/60:.1f} minutes")
    if speed > 0:
        logging.info(f"Processing time per article: {60/speed:.2f} seconds")


def handle_signal(signum, frame):
    """Signal handler for graceful shutdown."""
    logging.warning(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


def main():
    """Main execution function."""
    global start_time
    start_time = time.time()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    threads = []
    metrics_thread = None

    try:
        # Use a session factory for thread safety
        session_factory = SessionLocal
        url_data = []

        with session_factory() as session:  # Get URLs in a separate session
            url_data = fetch_random_urls(session)

        logging.debug(
            f"Starting to process {len(url_data)} URLs with {MAX_CONCURRENT} workers"
        )
        task_queue = Queue()

        def create_browser(playwright):
            return playwright.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
            )

        for i in range(MAX_CONCURRENT):
            thread = Thread(
                target=worker_thread,
                args=(task_queue, create_browser, session_factory),
                daemon=True,
            )
            threads.append(thread)
            thread.start()

        metrics_stop = Event()
        metrics_thread = Thread(
            target=quiet_metrics_monitor, args=(metrics_stop,), daemon=True
        )
        metrics_thread.start()

        for i, url in enumerate(url_data):
            task_queue.put((url, i))

        for _ in range(MAX_CONCURRENT):
            task_queue.put(None)

        while not task_queue.empty() and not shutdown_event.is_set():
            time.sleep(1)

        if shutdown_event.is_set():
            logging.warning("Shutting down gracefully...")

        for thread in threads:
            thread.join(timeout=5)
        metrics_stop.set()

        if metrics_thread:
            metrics_thread.join(timeout=2)

    except Exception as e:
        logging.error(f"Unhandled error: {e}", exc_info=True)
    finally:
        display_final_metrics()


if __name__ == "__main__":
    main()
