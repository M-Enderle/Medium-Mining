import argparse
import os
import random
import time
from datetime import datetime
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, Optional, List

from playwright.sync_api import Browser, BrowserContext, sync_playwright
from rich.console import Console, Group, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn, TaskID
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
from scraper.medium_helpers import (
    fetch_random_urls,
    persist_article_data,
    setup_signal_handlers,
    update_url_status,
    verify_its_an_article,
)

# Set up rich console and traceback
install_rich_traceback(show_locals=True)
console = Console()

# Global state variables
shutdown_event = Event()
completed_tasks = 0
start_time = 0
metrics_lock = Lock()
log_messages: List[str] = []
log_lock = Lock()

# Custom log function that stores messages for display
def log_message(message: str, level: str = "info") -> None:
    """
    Add a log message to the display.
    Args:
        message (str): Message to log
        level (str): Log level (info, warning, error, success)
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefixes = {
        "error": "[red][ERROR][/]",
        "warning": "[yellow][WARN][/]",
        "success": "[green][SUCCESS][/]",
        "info": "[blue][INFO][/]",
    }
    prefix = prefixes.get(level, prefixes["info"])
    
    with log_lock:
        log_messages.append(f"[dim]{timestamp}[/] {prefix} {message}")
        log_messages[:] = log_messages[-10:]


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
    return Panel(Text.from_markup(log_text), title="Log Messages", border_style="yellow")


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
            log_message(f"Processing URL: {url}")
            page.goto(url, wait_until="load", timeout=20000)
            page.wait_for_timeout(random.uniform(500, 2000))

            random_mouse_movement(page)

            if not verify_its_an_article(page):
                log_message(f"URL is not an article: {url}", "warning")
                update_url_status(session, url_id, "not_article", with_login=with_login)
                return

            persist_article_data(session, url_id, page, with_login)

            update_url_status(session, url_id, "success", with_login=with_login)
            log_message(f"Processed URL: {url}", "success")

            update_metrics()

    except Exception as e:
        log_message(f"Error processing URL {url}: {str(e)}", "error")
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
                        log_message(f"Error closing browser: {str(e)}", "error")

                task_queue.task_done()

        except Exception as e:
            if not shutdown.is_set():  # Only log if not shutting down
                log_message(f"Worker thread error: {str(e)}", "error")


def main(
    headless: bool = True,
    workers: int = 5,
    url_count: Optional[int] = None,
    with_login: bool = False,
    use_wandb: bool = False,
) -> None:
    """Main execution function for processing URLs with worker threads.

    Args:
        headless: Whether to run browser in headless mode
        workers: Number of worker threads
        url_count: Optional number of URLs to process
        with_login: Whether to login to Medium. Requires a login_state.json. Turning this on will scrape ONLY premium articles.
        use_wandb: Whether to use wandb for logging
    """
    global start_time, shutdown_event, completed_tasks

    assert not with_login or os.path.exists(
        "login_state.json"
    ), "Login state file not found. Please create a login_state.json file."

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
        log_message("Wandb requested but not available. Install with: pip install wandb", "warning")

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
            url_data = fetch_random_urls(session, url_count, with_login)

        total_urls = len(url_data)
        log_message(f"Starting to process {total_urls} URLs with {workers} workers", "info")

        # Create the progress display
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[bold green]{task.completed}/{task.total}"),
            TextColumn("[yellow]{task.percentage:>3.0f}%"),
            TextColumn("[cyan]{task.fields[speed]:.2f} articles/min"),
            expand=True
        )
        
        # Create the overall task
        overall_task_id = progress.add_task(
            "[white]Processing Articles", 
            total=total_urls,
            completed=0,
            speed=0.0
        )
        
        # Create a layout that combines progress and logs
        class DashboardLayout:
            def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
                progress_panel = Panel(progress, title="Progress", border_style="blue")
                log_panel = create_log_panel()
                yield Group(progress_panel, log_panel)
        
        # Start the dashboard display in a Live context
        with Live(DashboardLayout(), refresh_per_second=4, console=console):
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
            last_count = 0
            while not task_queue.empty() and not shutdown_event.is_set():
                time.sleep(0.25)
                
                # Update progress display
                with metrics_lock:
                    current_count = completed_tasks
                    elapsed = time.time() - start_time
                    
                speed = current_count / (elapsed / 60) if elapsed > 0 else 0
                
                progress.update(
                    overall_task_id, 
                    completed=current_count,
                    speed=speed
                )
                
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
        "--use_wandb",
        action="store_true",
        help="Use Weights & Biases for logging metrics",
    )

    args = parser.parse_args()

    main(
        headless=args.headless,
        workers=args.workers,
        url_count=args.url_count,
        with_login=args.with_login,
        use_wandb=args.use_wandb,
    )
