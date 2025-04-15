import argparse
import logging
import os
import random
import time
from datetime import datetime
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, Optional

import sentry_sdk
from playwright.sync_api import Browser, BrowserContext, sync_playwright
from sqlalchemy.orm import Session

import wandb
from database.database import URL, MediumArticle, SessionLocal
from scraper.medium_helpers import (
    fetch_random_urls,
    persist_article_data,
    setup_signal_handlers,
    update_url_status,
    verify_its_an_article,
)

sentry_sdk.init(
    dsn="https://aa404f7f4bacc96130a67102620177c6@o4509122866184192.ingest.de.sentry.io/4509122882240592",
    send_default_pii=True,
    traces_sample_rate=1.0,
)

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


def get_current_metrics() -> dict:
    """
    Get the current metrics for logging.
    Returns:
        dict: Dictionary of current metrics
    """
    global completed_tasks, start_time
    with metrics_lock:
        elapsed_time = time.time() - start_time
        articles_processed = completed_tasks

    if elapsed_time > 0:
        speed = articles_processed / (elapsed_time / 60)
        processing_time_per_article = 60 / speed if speed > 0 else 0
    else:
        speed = 0
        processing_time_per_article = 0

    # Fetch additional metrics from the database
    with SessionLocal() as session:
        total_articles = session.query(MediumArticle).count()
        free_articles = (
            session.query(MediumArticle).filter(MediumArticle.is_free == True).count()
        )
        premium_articles = (
            session.query(MediumArticle).filter(MediumArticle.is_free == False).count()
        )
        free_ratio = free_articles / total_articles if total_articles > 0 else 0
        premium_ratio = premium_articles / total_articles if total_articles > 0 else 0

    return {
        "articles_processed": articles_processed,
        "elapsed_minutes": elapsed_time / 60,
        "articles_per_minute": speed,
        "seconds_per_article": processing_time_per_article,
        "total_articles": total_articles,
        "free_articles": free_articles,
        "premium_articles": premium_articles,
        "free_ratio": free_ratio,
        "premium_ratio": premium_ratio,
    }


def wandb_logging_thread(shutdown: Event) -> None:
    """
    Thread to log metrics to wandb periodically.
    Args:
        shutdown (Event): Event to signal thread to stop
    """
    while not shutdown.is_set():
        try:
            metrics = get_current_metrics()
            wandb.log(metrics)
            logger.debug(f"Logged metrics to wandb: {metrics}")
        except Exception as e:
            logger.error(f"Error logging to wandb: {e}")

        # Sleep for 10 seconds or until shutdown is set
        for _ in range(10):
            if shutdown.is_set():
                break
            time.sleep(1)


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


def get_context(browser: Browser, with_login: bool) -> BrowserContext:
    """
    Randomize the user agent for the browser context.
    Args:
        browser (Browser): The Playwright browser instance.
        with_login (bool): Whether to login to Medium.
    Returns:
        BrowserContext: The browser context with a randomized user agent.
    """
    context_options = {
        "viewport": random.choice(
            [
                {"width": 390, "height": 844},
                {"width": 375, "height": 667},
                {"width": 414, "height": 896},
                {"width": 360, "height": 640},
                {"width": 412, "height": 915},
            ]
        ),
        "user_agent": random.choice(
            [
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (Linux; Android 8.0.0; SM-G950F Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.111 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",
            ]
        ),
        "locale": random.choice(
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
        "device_scale_factor": random.choice([1, 2]),
    }

    if with_login:
        context_options["storage_state"] = "login_state.json"

    context = browser.new_context(**context_options)

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
    url_data: tuple[int, str],
    browser: Browser,
    worker_idx: int,
    session: Session,
    with_login: bool,
) -> None:
    """
    Process a single article URL.
    Args:
        url_data (tuple[int, str]): Tuple containing URL ID and URL.
        browser (Browser): The Playwright browser instance.
        worker_idx (int): Index of the worker thread.
        session (Session): SQLAlchemy session for database operations.
        with_login (bool): Whether to login to Medium.
    """

    # stopping gracefully
    if shutdown_event.is_set():
        return

    url_id, url = url_data

    try:
        context = get_context(browser, with_login)

        with context.new_page() as page:
            logger.debug(f"Processing URL: {url}")
            page.goto(url, wait_until="load", timeout=20000)
            page.wait_for_timeout(random.uniform(500, 2000))

            random_mouse_movement(page)

            if not verify_its_an_article(page):
                logger.info(f"URL is not an article: {url}")
                update_url_status(session, url_id, "not_article", with_login=with_login)
                return

            persist_article_data(session, url_id, page, with_login)

            update_url_status(session, url_id, "success", with_login=with_login)
            logger.info(f"Processed URL: {url}")

            update_metrics()

    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        update_url_status(session, url_id, "error", str(e), with_login=with_login)


def worker_thread(
    task_queue: Queue,
    browser_factory: callable,
    session_factory: callable,
    shutdown: Event,
    with_login: bool = False,
) -> None:
    """
    Worker thread to process tasks from the queue.
    Args:
        task_queue (Queue): The queue containing tasks to process.
        browser_factory (callable): Function to create a browser instance.
        session_factory (callable): Function to create a session instance.
        shutdown (Event): Event to signal graceful shutdown.
        with_login (bool): Whether to login to Medium.
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
                        process_article(
                            url_data, browser, worker_idx, session, with_login
                        )
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
    headless: bool = True,
    workers: int = 5,
    url_count: Optional[int] = None,
    with_login: bool = False,
) -> None:
    """Main execution function for processing URLs with worker threads.

    Args:
        headless: Whether to run browser in headless mode
        workers: Number of worker threads
        url_count: Optional number of URLs to process
        with_login: Whether to login to Medium. Requires a login_state.json. Turning this on will scrape ONLY premium articles.
    """
    global start_time, shutdown_event

    assert not with_login or os.path.exists(
        "login_state.json"
    ), "Login state file not found. Please create a login_state.json file."

    # Set up signal handlers for graceful shutdown
    setup_signal_handlers(shutdown_event)

    start_time = time.time()
    task_queue = Queue()
    threads = []
    wandb_thread = None

    try:
        # Initialize database session factory
        session_factory = SessionLocal

        # Fetch URLs with proper session management
        with session_factory() as session:
            url_data = fetch_random_urls(session, url_count, with_login)

        logger.info(f"Starting to process {len(url_data)} URLs with {workers} workers")

        # Start wandb logging thread
        wandb_thread = Thread(
            target=wandb_logging_thread,
            args=(shutdown_event,),
            daemon=True,
        )
        wandb_thread.start()

        # Start worker threads
        for _ in range(workers):
            thread = Thread(
                target=worker_thread,
                args=(
                    task_queue,
                    lambda p: create_browser(p, headless),
                    session_factory,
                    shutdown_event,  # Pass the shutdown event to workers
                    with_login,
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
        if wandb_thread:
            wandb_thread.join(timeout=5)

        wandb.log(get_current_metrics())
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape articles from Medium.")
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    parser.add_argument(
        "--workers", type=int, default=5, help="Number of worker threads"
    )
    parser.add_argument(
        "--url_count", type=int, default=100, help="Number of URLs to process"
    )
    parser.add_argument(
        "--with_login",
        action="store_true",
        help="Login to Medium. Requires a login_state.json.",
    )

    args = parser.parse_args()

    # Initialize wandb in offline mode or with explicit finish
    wandb.init(
        project="medium-scraper",
        entity="JKU_",
        name=str(datetime.now().isoformat()),
        config=vars(args),
    )
    try:
        main(
            headless=args.headless,
            workers=args.workers,
            url_count=args.url_count,
            with_login=args.with_login,
        )
    finally:
        wandb.finish()
