import random
import time
from typing import Any, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page

from scraper.log_utils import log_message


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


def random_mouse_movement(page: Page) -> None:
    """
    Simulate random mouse movements and scrolling.
    Args:
        page (Page): The Playwright page instance.
    """
    time.sleep(random.uniform(0.5, 1.5))
    page.mouse.move(
        random.randint(0, 300), random.randint(0, 300), steps=random.randint(10, 20)
    )
    page.mouse.wheel(0, random.randint(100, 300))
    time.sleep(random.uniform(0.3, 0.8))


def close_overlay(page: Page) -> None:
    """
    Close the overlay if it exists.
    Args:
        page (Page): Playwright Page object.
    """
    try:
        page.evaluate(
            """
            () => {
                const overlay = document.querySelector("button[aria-label='close']");
                if (overlay) overlay.click();
            }
            """
        )
    except Exception as e:
        log_message(f"Error closing overlay: {e}", "debug")


def click_see_all_responses(page: Page, timeout: int = 1000):
    """
    Click the "See all responses" button if it exists.
    Args:
        page (Page): Playwright Page object.
        timeout (int): Timeout for the click action.
    Returns:
        bool: True if the button was clicked, False otherwise.
    """
    try:
        page.evaluate(
            """
        () => {
            const clickButton = () => {
                const button = document.querySelector('button[aria-label="responses"]');
                if (button) {
                    button.click();
                    return true;
                }
                return false;
            };
            
            // Try clicking up to 3 times
            if (clickButton()) return true;
            
            return new Promise((resolve) => {
                setTimeout(() => {
                    if (clickButton()) resolve(true);
                    else {
                        setTimeout(() => {
                            if (clickButton()) resolve(true);
                            else resolve(false);
                        }, 1000);
                    }
                }, 1000);
            });
        }
        """
        )
        return True
    except Exception as e:
        log_message(f"Failed to click responses button: {e}", "debug")
        return False


def scroll_to_load_comments(page: Page, max_scrolls: int = 100) -> None:
    """
    Scrolls down in the comment section until all comments are loaded or max_scrolls is reached.
    Args:
        page (Page): Playwright Page object.
        max_scrolls (int): Maximum number of scrolls to perform.
    """
    html = page.content()
    for _ in range(max_scrolls):
        try:
            page.evaluate(
                """
                () => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    if (dialog) dialog.lastElementChild.firstElementChild.scrollBy(0, 20000);
                }
            """
            )
            page.wait_for_timeout(1000)
            page.wait_for_load_state("load", timeout=5000)
            if page.content() == html:
                return
            html = page.content()
        except Exception as e:
            log_message(f"Scroll error on page {page.url}: {e}", "warning")
            return


def verify_its_an_article(page: Page) -> bool:
    """
    Verify if the page is an article.
    Args:
        page (Page): Playwright Page object.
    Returns:
        bool: True if the page is an article, False otherwise.
    """
    try:
        return page.query_selector("span[data-testid='storyReadTime']") is not None
    except Exception as e:
        log_message(f"Error verifying article: {e}", "debug")
        return False


def perform_interactive_login(storage_path: str = "login_state.json") -> None:
    """
    Open a visible browser window for manual Medium login and save storage state.

    Args:
        storage_path (str): Path to save the storage/cookies JSON.
    """
    try:
        from playwright.sync_api import sync_playwright  # local import to avoid global dependency

        log_message(
            "Launching browser for interactive Medium login. Login, then return here and press Enter.",
            "info",
        )
        with sync_playwright() as p:
            browser = create_browser(p, headless=False)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto("https://medium.com/m/signin", wait_until="load", timeout=30000)
            except Exception as e:
                log_message(f"Failed to open Medium sign-in page: {e}", "warning")

            try:
                input("After completing login in the opened browser, press Enter here to continue...")
            except EOFError:
                # In case stdin is not interactive; give the user some time
                log_message("Non-interactive terminal detected; waiting 30s before saving state.", "warning")
                page.wait_for_timeout(30000)

            try:
                context.storage_state(path=storage_path)
                log_message(f"Saved login storage state to: {storage_path}", "success")
            finally:
                browser.close()
    except Exception as e:
        log_message(f"Interactive login failed: {e}", "error")