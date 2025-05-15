import json
import re
import signal
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from html_to_markdown import convert_to_markdown
from playwright.sync_api import Page
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from database.database import URL, Author, Comment, MediumArticle, Sitemap
from scraper.log_utils import log_message, set_log_level
from scraper.playwright_helpers import (
    click_see_all_responses,
    close_overlay,
    scroll_to_load_comments,
    verify_its_an_article,
)

# Create a lock for database operations
db_persist_lock = threading.Lock()


def fetch_random_urls(
    session: Session, count: int, with_login: bool
) -> List[Tuple[int, str]]:
    """
    Fetch random URLs from the database that match the specified criteria.

    Criteria
    - URLs have not been scrapedP yet (last_crawled is None).
    - URLs are from sitemaps that contain "/posts/" in the URL.

    Args:
        session (Session): SQLAlchemy session object.
        count (int): Number of URLs to fetch.
        with_login (bool): Only include premium URLs that have not been crawled yet with login.
    Returns:
        List[Tuple[int, str]]: List of tuples containing URL ID and URL.
    """

    if not with_login:
        query = (
            session.query(URL.id, URL.url)
            .join(URL.sitemap)
            .filter(
                Sitemap.sitemap_url.like("%/posts/%"),
            )
            .filter(
                URL.last_crawled.is_(None),
            )
            # .order_by(URL.priority.desc())
            .limit(count)
        )
    else:
        query = (
            session.query(URL.id, URL.url)
            .join(URL.sitemap)
            .join(URL.article)
            .filter(Sitemap.sitemap_url.like("%/posts/%"))
            .filter(MediumArticle.is_free.is_(False))
            .filter(URL.with_login.is_(False))
            # .order_by(URL.priority.desc())
            .limit(count)
        )

    log_message(f"Fetching {count} random URLs from database", "debug")

    return query.all()


def update_url_status(
    session: Session,
    url_id: int,
    success: str,
    error: Optional[str] = None,
    with_login: bool = False,
) -> None:
    """
    Update the URL status in the database.
    Args:
        session (Session): SQLAlchemy session object.
        url_id (int): ID of the URL to update.
        success (bool): Whether the crawl was successful or not.
        error (Optional[str]): Optional error message if the crawl failed.
        with_login (bool): Whether the URL was processed with login.
    """

    try:
        url = session.query(URL).filter(URL.id == url_id).first()
        if url:
            url.last_crawled = datetime.now()
            url.crawl_status = success
            if error:
                url.crawl_failure_reason = error
            url.with_login = with_login
            session.commit()
            log_message(
                f"Updated URL {url_id} status: {success}, with_login: {with_login}",
                "debug",
            )
    except Exception as e:
        session.rollback()
        log_message(f"DB error for URL {url_id}: {e}", "error")


def extract_text(page: Page) -> str:
    """
    Extract text from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        str: Extracted text from the article.
    """
    article = page.query_selector("article")
    if not article:
        return ""

    return convert_to_markdown(article.inner_html()).split("Share", 1)[-1].strip()


def count_images(extracted_text: str) -> int:
    """
    Count the number of images in the article.
    Args:
        extracted_text (str): Extracted md text from the article.
    Returns:
        int: Number of images in the article.
    """
    return len(re.findall(r"!\[.*?\]\(.*?\)", extracted_text))


def extract_comments(page: Page) -> List[Dict[str, Any]]:
    """
    Extract comments from the article page.

    Args:
        page (Page): Playwright Page object.
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing comment data.
    """
    comments = []
    total_elements = 0
    filtered_elements = 0

    # Get all potential comment elements
    elements = page.locator("xpath=//pre/ancestor::div[5]").all()
    log_message(f"Found {len(elements)} potential comment elements", "debug")

    for el in elements:
        total_elements += 1

        # filter out answer comments based on border
        try:
            border_left = el.evaluate(
                "(el) => window.getComputedStyle(el.parentElement.parentElement).borderLeft"
            )
            if border_left == "3px solid rgb(242, 242, 242)":
                log_message(
                    f"Filtered answer comment with border: {border_left}", "debug"
                )
                filtered_elements += 1
                continue
        except Exception as e:
            log_message(f"Error checking comment border: {e}", "debug")
            continue

        comment = {
            "references_article": el.locator("p[id^='embedded-quote']").count() > 0,
            "username": None,
            "user_url": None,
            "text": None,
            "claps": None,
        }

        # Extract author information
        try:
            if authors := el.locator("a[href*='/@']").all():
                author = authors[0]
                author_url = author.get_attribute("href")
                if author_url:
                    # Extract username from URL (format: /@username or /@username?)
                    username_match = re.search(r"/@([^/?]+)", author_url)
                    if username_match:
                        comment["username"] = f"{username_match.group(1)}"
                        comment["user_url"] = author_url.split("?")[0]
            else:
                user_url_element = el.locator("a").first
                if user_url_element and "medium.com/" in (
                    user_url_element.get_attribute("href") or ""
                ):
                    comment["user_url"] = user_url_element.get_attribute("href").split(
                        "?"
                    )[0]
        except Exception as e:
            log_message(f"Error extracting comment author: {e}", "debug")

        # Extract comment text safely
        try:
            # Try a safer approach to get the comment text
            comment_text = el.evaluate(
                """
            (el) => {
                try {
                    // Navigate through the DOM structure more cautiously
                    const firstChild = el.firstElementChild;
                    if (!firstChild) return null;
                    
                    const firstInnerChild = firstChild.firstElementChild;
                    if (!firstInnerChild) return null;
                    
                    const secondInnerChild = firstInnerChild.firstElementChild;
                    if (!secondInnerChild) return null;
                    
                    const lastChild = secondInnerChild.lastElementChild;
                    if (!lastChild) return null;
                    
                    const prevSibling = lastChild.previousElementSibling;
                    if (!prevSibling) return null;
                    
                    return prevSibling.innerText;
                } catch (e) {
                    // Try alternative method to find text
                    const paragraphs = el.querySelectorAll('p:not([id^="embedded-quote"])');
                    if (paragraphs.length) {
                        return Array.from(paragraphs).map(p => p.innerText).join('\\n');
                    }
                    return null;
                }
            }
            """
            )

            if comment_text:
                comment["text"] = comment_text

            # Extract claps
            if claps := el.locator("div.pw-multi-vote-count").first:
                try:
                    comment["claps"] = int(claps.inner_text(timeout=500)) or 0
                except Exception as e:
                    comment["claps"] = 0
                    log_message(f"Failed to parse claps: {e}", "debug")
        except Exception as e:
            log_message(f"Error extracting comment text: {e}", "debug")

        if not comment["text"]:
            log_message("Skipping comment with no text", "debug")
            filtered_elements += 1
            continue

        comments.append(comment)

    log_message(
        f"Found {total_elements} total elements, filtered {filtered_elements}, kept {len(comments)} comments",
        "debug",
    )
    return comments


def extract_recommendation_urls(page: Page) -> List[str]:
    """
    Extract recommendation URLs from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        List[str]: List of recommendation URLs.
    """
    urls = []
    if not (header := page.locator("h2", has_text="Recommended from Medium").first):
        return urls

    if not (container := header.locator("xpath=..")):
        return urls

    for article in container.locator('div[role="link"]').all():
        try:
            if url := (article.get_attribute("data-href") or ""):
                urls.append(url.split("?")[0])
        except:
            pass

    return urls


def extract_tags(page: Page) -> List[str]:
    """
    Extract tags from an article page.

    Args:
        page (Page): Playwright Page object.
    Returns:
        List[str]: List of tag strings.
    """
    tags = []
    try:
        for tag in page.query_selector_all('a[href*="/tag/"]') or []:
            try:
                if tag_text := tag.inner_text().strip():
                    tags.append(tag_text)
            except Exception as e:
                log_message(f"Failed to process tag: {e}", "warning")
    except Exception as e:
        log_message(f"Failed to extract tags: {e}", "warning")
    return tags


def get_or_create_author(
    session: Session, username: Optional[str] = None, medium_url: Optional[str] = None
) -> Author:
    """
    Get or create an author in the database.
    Args:
        session (Session): SQLAlchemy session object.
        username (str): User Name of the author.
        medium_url (Optional[str]): Medium URL of the author.
    Returns:
        Author: The author object.
    """
    if not username and not medium_url:
        return None

    if username:
        username = username.strip("@")

    author = (
        session.query(Author)
        .filter(
            or_(
                and_(Author.username == username, Author.username.isnot(None)),
                and_(Author.medium_url == medium_url, Author.medium_url.isnot(None)),
            )
        )
        .first()
    )
    if not author:
        if not username:
            username_match = re.search(r"^https://([^/]+)\.medium\.com", medium_url)
            if username_match is not None:
                username = username_match.group(1)
        author = Author(
            id=(session.query(func.max(Author.id)).scalar() or 0) + 1,
            username=username,
            medium_url=medium_url or f"https://medium.com/@{username}",
        )
        session.add(author)
        session.commit()
        log_message(
            f"Created new author: {author.username} ({author.medium_url})", "debug"
        )
    else:
        log_message(
            f"Found existing author: {author.username} ({author.medium_url})", "debug"
        )
    return author


def get_read_time(page: Page) -> Optional[int]:
    """
    Get the read time from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        Optional[int]: Read time in minutes, or None if not found.
    """
    try:
        read_time = page.query_selector("span[data-testid='storyReadTime']")
        if read_time:
            return int(read_time.inner_text().split()[0])
    except Exception as e:
        log_message(f"Error getting read time: {e}", "debug")
    return None


def get_claps(page: Page) -> Optional[int]:
    """
    Get the number of claps from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        Optional[int]: Number of claps, or None if not found.
    """
    if claps_element := page.query_selector("div.pw-multi-vote-count button"):
        try:
            claps_text = claps_element.inner_text()
            if "K" in claps_text:
                return int(float(claps_text.replace("K", "").strip()) * 1000)
            elif "M" in claps_text:
                return int(float(claps_text.replace("M", "").strip()) * 1000000)
            else:
                return int(claps_text.replace(",", "").strip())
        except ValueError:
            log_message("Failed to convert claps text to integer", "debug")
            return None


def get_comments_count(page: Page) -> Optional[int]:
    """
    Get the number of comments from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        Optional[int]: Number of comments, or None if not found.
    """
    if comments_element := page.query_selector("h2:has-text('Responses')"):
        try:
            comments_text = comments_element.inner_text()
            if comments_text == "No responses yet":
                return None
            comments_count = re.search(r"\d+", comments_text).group(0)
            return int(comments_count)
        except (AttributeError, ValueError):
            log_message("Failed to extract comments count", "debug")
            return None
        except ValueError:
            log_message("Failed to convert comments text to integer", "debug")
            return None


def is_paid_article(page: Page) -> bool:
    """
    Check if the article is a paid article.
    Args:
        page (Page): Playwright Page object.
    Returns:
        bool: True if the article is paid, False otherwise.
    """
    try:
        return page.query_selector("article.meteredContent") is not None
    except Exception as e:
        log_message(f"Error checking paid article: {e}", "debug")
        return False


def extract_metadata(page: Page) -> Dict[str, Any]:
    """
    Extract metadata from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        Dict[str, Any]: Dictionary containing metadata.
    """

    if script := page.query_selector('script[type="application/ld+json"]'):
        json_data = json.loads(script.inner_text())
        article_data = {
            "type": json_data.get("@type"),
            "username": (
                re.search(r"@[^/]+", json_data.get("author", {}).get("url", "")).group(
                    0
                )
                if re.search(r"@[^/]+", json_data.get("author", {}).get("url", ""))
                else None
            ),
            "author_url": json_data.get("author", {}).get("url"),
            "date_created": json_data.get("dateCreated"),
            "date_modified": json_data.get("dateModified"),
            "date_published": json_data.get("datePublished"),
            "description": json_data.get("description"),
            "publisher_type": json_data.get("publisher", {}).get("@type"),
            "title": json_data.get("headline"),
        }
    else:
        log_message("No metadata script found on the page.", "warning")
        return {}

    return article_data


def persist_article_data(
    session: Session,
    url_id: int,
    page: Page,
    with_login: bool,
    insert_recc: bool = False,
) -> bool:

    page.wait_for_load_state("networkidle")

    close_overlay(page)

    metadata = extract_metadata(page)
    tags = extract_tags(page)

    assert metadata.get("title"), "JSON metadata is empty"

    full_text = extract_text(page)
    claps = get_claps(page) or 0
    comments_count = get_comments_count(page) or 0
    is_free = not is_paid_article(page)
    read_time = get_read_time(page)
    recc = extract_recommendation_urls(page)
    num_images = count_images(full_text)

    click_see_all_responses(page)
    scroll_to_load_comments(page)
    page.wait_for_timeout(500)
    comments = extract_comments(page)

    with db_persist_lock:
        try:

            author = get_or_create_author(
                session,
                metadata.get("username"),
                metadata.get("author_url"),
            )

            if not author:
                log_message("No author found for the article.", "warning")

            article = (
                session.query(MediumArticle)
                .filter(MediumArticle.url_id == url_id)
                .first()
            )
            if article:
                article.full_article_text = full_text
                article.claps = claps
                article.comments_count = comments_count
                article.num_images = num_images
            else:
                article = MediumArticle(
                    url_id=url_id,
                    title=metadata.get("title"),
                    author_id=author.id if author else None,
                    date_created=metadata.get("date_created"),
                    date_modified=metadata.get("date_modified"),
                    date_published=metadata.get("date_published"),
                    description=metadata.get("description"),
                    publisher_type=metadata.get("publisher_type"),
                    is_free=is_free,
                    claps=claps,
                    comments_count=comments_count,
                    full_article_text=full_text,
                    read_time=read_time,
                    type=metadata.get("type"),
                    tags=tags,
                    num_images=num_images,
                )

            session.add(article)
            session.commit()

            if with_login:
                return True

            log_message(f"Found {len(comments)} comments", "info")

            if comments:
                for comment in comments:
                    author = get_or_create_author(
                        session,
                        comment.get("username"),
                        comment.get("user_url"),
                    )
                    if (
                        session.query(Comment)
                        .filter(Comment.article_id == article.id)
                        .filter(Comment.author_id == author.id if author else None)
                        .first()
                    ):
                        continue

                    try:
                        comment_obj = Comment(
                            id=(session.query(func.max(Comment.id)).scalar() or 0) + 1,
                            article_id=article.id,
                            author_id=author.id if author else None,
                            text=comment.get("text"),
                            claps=comment.get("claps"),
                            references_article=comment.get("references_article"),
                        )
                        session.add(comment_obj)
                        session.commit()
                        session.flush()
                    except Exception as e:
                        session.rollback()
                        log_message(f"Failed to persist comment: {e}", "error")
                        continue

            if insert_recc:
                for url in recc:
                    if not session.query(URL).filter(URL.url == url).first():
                        new_url = URL(
                            id=session.query(func.max(URL.id)).scalar() + 1,
                            url=url,
                            priority=1.0,
                        )
                        session.add(new_url)
                        session.commit()
                    else:
                        session.query(URL).filter(URL.url == url).update(
                            {"priority": URL.priority + 0.1}
                        )

            return True

        except Exception as e:
            session.rollback()
            log_message(f"Failed to persist article data: {e}", "error")
            return False


def setup_signal_handlers(shutdown_event: threading.Event) -> None:
    """
    Set up signal handlers for graceful shutdown.
    Args:
        shutdown_event (threading.Event): Event to signal graceful shutdown.
    """

    def handler(sig, frame):
        log_message("Received signal. Shutting down gracefully...", "warning")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


if __name__ == "__main__":
    import time

    from playwright.sync_api import sync_playwright

    # Set the log level for more detailed output
    set_log_level("debug")
    log_message("Starting test run of comment extraction", "info")

    # Set up a simple shutdown event for testing
    test_shutdown_event = threading.Event()

    with sync_playwright() as p:
        # Launch mobile browser with appropriate viewport and user agent
        mobile_viewport = {"width": 375, "height": 812}  # iPhone X dimensions
        mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"

        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport=mobile_viewport,
            user_agent=mobile_user_agent,
            device_scale_factor=2.0,
        )
        page = context.new_page()

        try:
            # Navigate to the test article
            url = "https://medium.com/coinmonks/1k-to-10k-crypto-challenge-week-4-massive-portfolio-changes-6bafb07c7f61"
            log_message(f"Navigating to {url} on mobile browser", "info")
            page.goto(url)

            # Wait for the page to load
            page.wait_for_load_state("networkidle")

            # Verify it's an article
            if not verify_its_an_article(page):
                log_message("This page is not a Medium article", "error")
                browser.close()
                exit(1)

            close_overlay(page)

            # Try to click on the responses button to show comments
            log_message("Attempting to load comments...", "info")
            click_see_all_responses(page)

            # Scroll to load all comments
            log_message("Scrolling to load all comments...", "info")
            scroll_to_load_comments(page, 10)

            page.wait_for_timeout(1000)

            # Extract comments
            log_message("Extracting comments...", "info")
            comments = extract_comments(page)

            for comment in comments:
                if not (comment.get("username") or comment.get("user_url")):
                    log_message(
                        f"Comment without author information: {comment}", "warning"
                    )

            log_message(f"Found {len(comments)} comments in total", "info")
            for i, comment in enumerate(comments):
                log_message(f"Comment {i+1}: {comment.get('text')[:100]}...", "info")

        except Exception as e:
            log_message(f"Error during test: {e}", "error")

        finally:
            log_message("Closing browser...", "info")
            browser.close()
