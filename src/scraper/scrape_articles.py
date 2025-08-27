import argparse
import os
import random
import time
from datetime import datetime
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, List, Optional

from playwright.sync_api import Browser, BrowserContext, sync_playwright
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback
from sqlalchemy.orm import Session

try:
    import wandb

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

from database.database import URL, MediumArticle, SessionLocal
from scraper.log_utils import log_lock, log_message, log_messages, set_log_level
from scraper.medium_helpers import (
    fetch_random_urls,
    fetch_failed_urls,
    persist_article_data,
    setup_signal_handlers,
    update_url_status,
)
from scraper.playwright_helpers import (
    create_browser,
    get_context,
    random_mouse_movement,
    verify_its_an_article,
    perform_interactive_login,
)

# Set up rich console and traceback
install_rich_traceback(show_locals=True)
console = Console()

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
    Get current metrics for logging.
    Returns:
        dict: Dictionary of current metrics
    """
    global completed_tasks, start_time
    with metrics_lock:
        elapsed_time = time.time() - start_time
        articles_processed = completed_tasks

    speed = articles_processed / (elapsed_time / 60) if elapsed_time > 0 else 0
    processing_time_per_article = 60 / speed if speed > 0 else 0

    with SessionLocal() as session:
        total_articles = session.query(MediumArticle).count()
        free_articles = session.query(MediumArticle).filter_by(is_free=True).count()
        premium_articles = session.query(MediumArticle).filter_by(is_free=False).count()
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


def create_metrics_display(metrics: dict) -> Panel:
    """Create a simplified metrics display panel."""
    table = Table(show_header=False, expand=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="left")

    metrics_data = [
        ("Articles Processed", f"{metrics.get('articles_processed', 0):,}"),
        ("Processing Speed", f"{metrics.get('articles_per_minute', 0):.1f}/min"),
        ("Time per Article", f"{metrics.get('seconds_per_article', 0):.1f}s"),
        ("Total Articles", f"{metrics.get('total_articles', 0):,}"),
        ("Free Articles", f"{metrics.get('free_articles', 0):,}"),
        ("Premium Articles", f"{metrics.get('premium_articles', 0):,}"),
        ("Elapsed Time", f"{metrics.get('elapsed_minutes', 0):.1f}min"),
    ]

    for metric, value in metrics_data:
        table.add_row(metric, value)

    return Panel(table, title="Medium Scraper Progress", border_style="blue")


def create_log_panel() -> Panel:
    """
    Create a panel with the latest log messages.
    Returns:
        Panel: A panel with formatted log messages
    """
    with log_lock:
        # Get a copy of current log messages
        messages = log_messages.copy()

    log_text = "\n".join(messages) if messages else "[dim]No log messages yet...[/]"
    return Panel(
        Text.from_markup(log_text), title="Log Messages", border_style="yellow"
    )


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
    context = None

    try:
        log_message(f"Worker {worker_idx} starting to process URL ID {url_id}", "debug")
        context = get_context(browser, with_login)

        with context.new_page() as page:
            log_message(f"Processing URL: {url}")

            # Navigate to the URL with proper error handling
            try:
                log_message(f"Opening URL with timeout of 20000ms", "debug")
                page.goto(url, wait_until="load", timeout=20000)
                page.wait_for_timeout(random.uniform(500, 2000))
            except Exception as e:
                log_message(f"Error loading URL {url}: {str(e)}", "error")
                update_url_status(
                    session, url_id, "navigation_error", str(e), with_login=with_login
                )
                return

            # Add random mouse movement to appear more human-like
            try:
                random_mouse_movement(page)
            except Exception as e:
                log_message(f"Error during random mouse movement: {str(e)}", "debug")
                # Continue despite mouse movement error

            # Verify the page is an article
            try:
                log_message(f"Verifying if URL is an article: {url}", "debug")
                if not verify_its_an_article(page):
                    log_message(f"URL is not an article: {url}", "warning")
                    update_url_status(
                        session, url_id, "not_article", with_login=with_login
                    )
                    return
            except Exception as e:
                log_message(f"Error verifying article: {str(e)}", "error")
                update_url_status(
                    session, url_id, "verification_error", str(e), with_login=with_login
                )
                return

            # Persist article data
            try:
                log_message(f"Persisting article data for URL: {url}", "debug")
                if not persist_article_data(session, url_id, page, with_login):
                    log_message(
                        f"Failed to persist article data for URL: {url}", "error"
                    )
                    update_url_status(
                        session, url_id, "persist_error", with_login=with_login
                    )
                    return
            except Exception as e:
                log_message(f"Error persisting article data: {str(e)}", "error")
                update_url_status(
                    session, url_id, "persist_error", str(e), with_login=with_login
                )
                return

            # Update URL status and metrics
            update_url_status(session, url_id, "success", with_login=with_login)
            log_message(f"Processed URL: {url}", "success")
            update_metrics()

    except Exception as e:
        log_message(f"Error processing URL {url}: {str(e)}", "error")
        log_message(f"Exception details: {repr(e)}", "debug")
        update_url_status(session, url_id, "error", str(e), with_login=with_login)
    finally:
        # Ensure context is closed to prevent memory leaks
        if context:
            try:
                context.close()
            except Exception as e:
                log_message(f"Error closing context: {str(e)}", "debug")


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
    log_message("Worker thread starting", "debug")

    while not shutdown.is_set():
        try:
            task = task_queue.get(timeout=1)
            if task is None:
                log_message("Received termination signal, stopping worker", "debug")
                task_queue.task_done()
                break

            url_data, worker_idx = task
            log_message(
                f"Got task for URL ID {url_data[0]} assigned to worker {worker_idx}",
                "debug",
            )

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
                        log_message(f"Error closing browser: {str(e)}", "error")

            task_queue.task_done()
            log_message(f"Completed task for URL ID {url_data[0]}", "debug")

        except Exception as e:
            if not shutdown.is_set():  # Only log if not shutting down
                log_message(f"Worker thread error: {str(e)}", "error")
                log_message(f"Stack trace: {repr(e)}", "debug")


def main(
    headless: bool = True,
    workers: int = 5,
    url_count: Optional[int] = None,
    with_login: bool = False,
    use_wandb: bool = False,
    log_level: str = "info",
    retry_failed: bool = False,
) -> None:
    """Main execution function for processing URLs with worker threads.

    Args:
        headless: Whether to run browser in headless mode
        workers: Number of worker threads
        url_count: Optional number of URLs to process
        with_login: Whether to login to Medium. Requires a login_state.json. Turning this on will scrape ONLY premium articles.
        use_wandb: Whether to use wandb for logging metrics
        log_level: Log verbosity level (error, warning, success, info, debug)
    """
    global start_time, shutdown_event, completed_tasks

    # Set the log level and log the status
    log_status = set_log_level(log_level)
    log_message(log_status, "info")

    if with_login and not os.path.exists("login_state.json"):
        log_message(
            "with_login enabled but no login_state.json found. Starting interactive login...",
            "warning",
        )
        perform_interactive_login("login_state.json")
        if not os.path.exists("login_state.json"):
            raise AssertionError(
                "Login state file not created. Aborting. Rerun with --with_login to retry."
            )

    # Initialize wandb if enabled
    if use_wandb and WANDB_AVAILABLE:
        wandb.init(
            project="medium-scraper",
            entity="JKU_",
            name=str(datetime.now().isoformat()),
            config={
                "headless": headless,
                "workers": workers,
                "url_count": url_count,
                "with_login": with_login,
            },
        )
    elif use_wandb and not WANDB_AVAILABLE:
        log_message(
            "Wandb requested but not available. Install with: pip install wandb",
            "warning",
        )

    # Set up signal handlers for graceful shutdown
    setup_signal_handlers(shutdown_event)

    start_time = time.time()
    task_queue = Queue()
    threads = []

    # Reset completed tasks counter
    completed_tasks = 0

    try:
        # Initialize database session factory
        session_factory = SessionLocal

        # Fetch URLs with proper session management
        with session_factory() as session:
            if retry_failed:
                url_data = fetch_failed_urls(session, url_count, with_login)
            else:
                url_data = fetch_random_urls(session, url_count, with_login)

        total_urls = len(url_data)
        log_message(
            f"Starting to process {total_urls} URLs with {workers} workers", "info"
        )

        # Create the progress display
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[bold green]{task.completed}/{task.total}"),
            TextColumn("[yellow]{task.percentage:>3.0f}%"),
            TextColumn("[cyan]{task.fields[speed]:.2f} articles/min"),
            expand=True,
        )

        # Create the overall task
        overall_task_id = progress.add_task(
            "[white]Processing Articles", total=total_urls, completed=0, speed=0.0
        )

        # Create a layout that combines progress and logs
        class DashboardLayout:
            def __rich_console__(
                self, console: Console, options: ConsoleOptions
            ) -> RenderResult:
                progress_panel = Panel(progress, title="Progress", border_style="blue")
                log_panel = create_log_panel()
                metrics_panel = create_metrics_display(get_current_metrics())
                yield Group(progress_panel, metrics_panel, log_panel)

        # Start the dashboard display in a Live context
        with Live(DashboardLayout(), refresh_per_second=4, console=console):
            # Start worker threads
            for i in range(workers):
                thread = Thread(
                    target=worker_thread,
                    args=(
                        task_queue,
                        lambda p: create_browser(p, headless),
                        session_factory,
                        shutdown_event,
                        with_login,
                    ),
                    daemon=True,
                )
                threads.append(thread)
                thread.start()

            # Enqueue tasks
            for i, url in enumerate(url_data):
                task_queue.put(((url[0], url[1]), i % workers))

            # Add termination signals after all tasks
            for _ in range(workers):
                task_queue.put(None)

            # Monitor task completion
            last_count = 0
            while (
                any(thread.is_alive() for thread in threads)
                and not shutdown_event.is_set()
            ):
                time.sleep(0.25)

                # Update progress display
                with metrics_lock:
                    current_count = completed_tasks
                    elapsed = time.time() - start_time

                speed = current_count / (elapsed / 60) if elapsed > 0 else 0

                progress.update(overall_task_id, completed=current_count, speed=speed)

                # Update wandb if enabled
                if use_wandb and WANDB_AVAILABLE and current_count != last_count:
                    metrics = get_current_metrics()
                    wandb.log(metrics)
                    last_count = current_count

            if shutdown_event.is_set():
                log_message("Shutting down gracefully...", "warning")

    except Exception as e:
        log_message(f"Unhandled error: {str(e)}", "error")
        console.print_exception(show_locals=True)
        raise

    finally:
        # Signal threads to stop if not already done
        if not shutdown_event.is_set():
            shutdown_event.set()

        # Cleanup threads
        for thread in threads:
            thread.join(timeout=5)

        # Final metrics
        metrics = get_current_metrics()
        console.print("\n[bold green]Final Metrics:[/]")
        console.print(create_metrics_display(metrics))

        if use_wandb and WANDB_AVAILABLE:
            wandb.log(metrics)
            wandb.finish()


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
    parser.add_argument(
        "--retry_failed",
        action="store_true",
        help="Retry URLs that previously failed instead of new ones",
    )
    parser.add_argument(
        "--use_wandb",
        action="store_true",
        help="Use Weights & Biases for logging metrics",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        choices=["error", "warning", "success", "info", "debug"],
        default="info",
        help="Set logging verbosity level",
    )

    args = parser.parse_args()

    main(
        headless=args.headless,
        workers=args.workers,
        url_count=args.url_count,
        with_login=args.with_login,
        use_wandb=args.use_wandb,
        log_level=args.log_level,
        retry_failed=args.retry_failed,
    )
