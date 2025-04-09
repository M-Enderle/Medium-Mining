import json
import logging
import re
import signal
import threading
from datetime import datetime
from pprint import pprint
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Page
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from database.database import (URL, Author, Comment, MediumArticle, Sitemap,
                               get_session)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_random_urls(session: Session, count: int) -> List[Tuple[int, str]]:
    """
    Fetch random URLs from the database that match the specified criteria.

    Criteria:
    - URLs have not been scraped yet (last_crawled is None).
    - URLs are from sitemaps that contain "/posts/" in the URL.

    Args:
        session (Session): SQLAlchemy session object.
        count (int): Number of URLs to fetch.
    Returns:
        List[Tuple[int, str]]: List of tuples containing URL ID and URL.
    """

    query = (
        session.query(URL.id, URL.url)
        .join(URL.sitemap)
        .filter(
            or_(
                Sitemap.sitemap_url.like("%/posts/%"),
            )
        )
        .filter(
            URL.last_crawled.is_(None),
        )
        .order_by(URL.priority.desc())
        .limit(count)
    )

    logger.debug(f"Fetching {count} random URLs from database")

    return query.all()


def update_url_status(
    session: Session, url_id: int, success: bool, error: Optional[str] = None
) -> None:
    """
    Update the URL status in the database.
    Args:
        session (Session): SQLAlchemy session object.
        url_id (int): ID of the URL to update.
        success (bool): Whether the crawl was successful or not.
        error (Optional[str]): Optional error message if the crawl failed.
    """

    try:
        url = session.query(URL).filter(URL.id == url_id).first()
        if url:
            url.last_crawled = datetime.now()
            url.crawl_status = "Successful" if success else "Failed"
            if error:
                url.crawl_failure_reason = error
            session.commit()
            logger.debug(f"Updated URL {url_id} status: {success}")
    except Exception as e:
        session.rollback()
        logger.error(f"DB error for URL {url_id}: {e}")


def extract_text(page: Page) -> str:
    """
    Extract text from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        str: Extracted text from the article.
    """
    paragraphs = page.query_selector_all(
        "article p[data-selectable-paragraph]"
    ) or page.query_selector_all("article p")
    return "\n".join(p.inner_text() for p in paragraphs if p.inner_text())


def click_see_all_responses(page: Page, timeout: int = 1000) -> bool:
    """
    Click the "See all responses" button if it exists.
    Args:
        page (Page): Playwright Page object.
        timeout (int): Timeout for the click action.
    Returns:
        bool: True if the button was clicked, False otherwise.
    """
    try:
        page.wait_for_selector('button:has-text("See all responses")', timeout=timeout)
        button = page.query_selector('button:has-text("See all responses")')
        if button and button.is_visible():
            button.click(timeout=timeout)
            page.wait_for_load_state("load", timeout=timeout)
            return True
    except Exception as e:
        logger.debug(f"Failed to click responses button: {e}")
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
            page.wait_for_timeout(500)
            page.wait_for_load_state("load", timeout=5000)
            if page.content() == html:
                return
            html = page.content()
        except Exception as e:
            logger.warning(f"Scroll error on page {page.url}: {e}")
            return


def extract_comments(page: Page) -> List[Dict[str, Any]]:
    """
    Extract comments from the article page. This is dont by

    Args:
        page (Page): Playwright Page object.
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing comment data.
    """
    comments = []
    for el in page.locator("xpath=//pre/ancestor::div[5]").all():
        if "l" not in el.evaluate(
            "(el) => el.parentElement.parentElement.classList.value"
        ):
            continue

        # TODO check that the author is handled correctly
        comment = {
            "references_article": el.locator("p[id^='embedded-quote']").count() > 0,
            "username": None,
            "author_name": None,
            "medium_username": None,
            "text": None,
            "claps": None,
            "full_html_text": el.inner_text(),
        }

        if authors := el.locator("a[href^='/@']").all():
            href = authors[0].get_attribute("href")
            username = href.split("?")[0].split("/")[1] if href else "Unknown"
            comment.update(username=username, medium_username=username)
            try:
                if (name := authors[0].inner_text().strip()) and name != username:
                    comment["author_name"] = name
            except:
                pass

        try:
            comment["text"] = el.evaluate(
                "(el) => el.firstElementChild.firstElementChild.firstElementChild.lastElementChild.previousElementSibling.innerText"
            )
            if claps := el.locator("div.pw-multi-vote-count").first:
                try:
                    comment["claps"] = int(claps.inner_text(timeout=500)) or 0
                except Exception as e:
                    comment["claps"] = 0
                    logger.debug(f"Failed to parse claps: {e}")
        except Exception as e:
            logger.debug(f"Error extracting comment text: {e}")

        comments.append(comment)
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
                logger.warning(f"Failed to process tag: {e}")
    except Exception as e:
        logger.warning(f"Failed to extract tags: {e}")
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
            username=username, medium_url=medium_url or f"https://medium.com/{username}"
        )
        session.add(author)
        session.commit()
        logger.debug(f"Created new author: {author.username} ({author.medium_url})")
    else:
        logger.debug(f"Found existing author: {author.username} ({author.medium_url})")
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
        logger.debug(f"Error getting read time: {e}")
    return None


def get_claps(page: Page) -> Optional[int]:
    """
    Get the number of claps from the article page.
    Args:
        page (Page): Playwright Page object.
    Returns:
        Optional[int]: Number of claps, or None if not found.
    """
    if claps_element := page.query_selector("div.pw-multi-vote-count p"):
        try:
            claps_text = claps_element.inner_text()
            if "K" in claps_text:
                return int(float(claps_text.replace("K", "").strip()) * 1000)
            elif "M" in claps_text:
                return int(float(claps_text.replace("M", "").strip()) * 1000000)
            else:
                return int(claps_text.replace(",", "").strip())
        except ValueError:
            logger.debug("Failed to convert claps text to integer")
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
        logger.debug(f"Error checking paid article: {e}")
        return False


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
        logger.debug(f"Error closing overlay: {e}")


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
        logger.warning("No metadata script found on the page.")
        return {}

    return article_data


def persist_article_data(session: Session, url_id: int, page: Page) -> bool:
    try:
        close_overlay(page)

        metadata = extract_metadata(page)

        assert metadata.get("title"), "JSON metadata is empty"

        comments_count = None
        if click_see_all_responses(page):
            scroll_to_load_comments(page)
            comments = extract_comments(page)
            comments_count = len(comments)

        author = get_or_create_author(
            session,
            metadata.get("username"),
            metadata.get("author_url"),
        )

        tags = extract_tags(page)

        if not author:
            logger.warning("No author found for the article.")

        article = MediumArticle(
            url_id=url_id,
            title=metadata.get("title"),
            author_id=author.id if author else None,
            date_created=metadata.get("date_created"),
            date_modified=metadata.get("date_modified"),
            date_published=metadata.get("date_published"),
            description=metadata.get("description"),
            publisher_type=metadata.get("publisher_type"),
            is_free=not is_paid_article(page),
            claps=get_claps(page) or 0,
            comments_count=comments_count or 0,
            full_article_text=extract_text(page),
            read_time=get_read_time(page),
            type=metadata.get("type"),
            tags=tags,
        )

        session.add(article)
        session.commit()

        if comments_count is not None:
            for comment in comments:
                author = get_or_create_author(
                    session,
                    comment.get("username"),
                )
                comment_obj = Comment(
                    article_id=article.id,
                    author_id=author.id if author else None,
                    text=comment.get("text"),
                    full_text=comment.get("full_html_text"),
                    claps=comment.get("claps"),
                    references_article=comment.get("references_article"),
                )
                session.add(comment_obj)

        session.commit()

        recommendation_urls = extract_recommendation_urls(page)
        recommendation_urls = set(recommendation_urls)
        max_id = session.query(func.max(URL.id)).scalar()
        count = 0
        for url in recommendation_urls:
            if not session.query(URL).filter(URL.url == url).first():
                new_url_id = max_id + count + 1
                count += 1
                new_url = URL(
                    id=new_url_id, url=url, found_on_url_id=url_id, priority=1.1
                )
                session.add(new_url)
                logger.debug(f"New URL added: {url}")
            else:
                session.query(URL).filter(URL.url == url).update(
                    {"priority": URL.priority + 0.1}
                )

        session.commit()

        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to persist article data: {e}", exc_info=True)
        return False


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
        logger.debug(f"Error verifying article: {e}")
        return False


def setup_signal_handlers(shutdown_event: threading.Event) -> None:
    """
    Set up signal handlers for graceful shutdown.
    Args:
        shutdown_event (threading.Event): Event to signal shutdown.
    """

    def handler(sig, frame):
        shutdown_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        session = get_session()
        # mobile
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 375, "height": 812},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1",
        )
        page = context.new_page()
        page.goto("https://medium.com/comsystoreply/angular-elements-569025b65c69")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        assert verify_its_an_article(page) is True

        # test functions
        assert extract_text(page)
        assert len(extract_tags(page)) > 0
        assert len(extract_recommendation_urls(page)) == 6
        assert get_read_time(page) is not None

        metadata = extract_metadata(page)
        assert len(metadata.keys()) > 0
        assert "title" in metadata

        author = metadata.get("username")
        assert author is not None

        # test persist_article_data
        assert persist_article_data(session, 1, page) is True

        # negtive example for verify_its_an_article
        page.goto("https://medium.com/@kevinchisholm")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        assert verify_its_an_article(page) is False

        # close
        page.close()
        browser.close()

    session.close()
