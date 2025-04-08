import json
import logging
import signal
import threading
from datetime import datetime
from typing import Any, Dict, List, Tuple

from playwright.sync_api import Page
from sqlalchemy import func

from database.database import URL, Comment, MediumArticle

# Configure logging (Keep it simple)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default number of URLs to fetch
URLS_TO_FETCH = 50


def fetch_random_urls(session, count=None) -> List[Tuple[int, str]]:
    """Fetch random URLs from the database."""
    # query = session.query(URL.id, URL.url).filter(URL.last_crawled == None)
    query = session.query(URL.id, URL.url)

    # Use the provided count, or fall back to the global URLS_TO_FETCH
    limit = count if count is not None else URLS_TO_FETCH
    query = query.order_by(func.random()).limit(limit)

    logger.debug(f"Fetching {limit} random URLs from database")
    return query.all()


def update_url_status(session, url_id: int, success: bool):
    """Update the URL's last_crawled timestamp and crawl_status."""
    try:
        url = session.query(URL).filter(URL.id == url_id).first()
        if url:
            url.last_crawled = datetime.now()
            url.crawl_status = "Successful" if success else "Failed"
            session.commit()
            logger.debug(f"Updated URL {url_id} status: {success}")
    except Exception as e:
        session.rollback()
        logger.error(f"DB error for URL {url_id}: {e}")


def extract_text(page: Page) -> str:
    """Extract full article text."""
    paragraphs = page.query_selector_all(
        "article p[data-selectable-paragraph]"
    ) or page.query_selector_all("article p")
    return "\n".join(p.inner_text() for p in paragraphs if p.inner_text())


def click_see_all_responses(page: Page) -> bool:
    """Click 'See all responses' button."""
    try:
        button = page.query_selector('button:has-text("See all responses")')
        if button:
            button.click(timeout=10000)
            page.wait_for_load_state("load", timeout=10000)
            return True
    except Exception as e:
        logger.warning(f"Failed to click responses button: {e}")
    return False


def scroll_to_load_comments(page: Page, max_scrolls: int = 100) -> None:
    """Scroll to load all comments."""
    html = page.content()
    for _ in range(max_scrolls):
        try:
            page.evaluate(
                """() => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (dialog) dialog.lastElementChild.firstElementChild.scrollBy(0, 20000);
            }"""
            )
            page.wait_for_timeout(500)
            page.wait_for_load_state("load", timeout=5000)
            if page.content() == html:
                break
            html = page.content()
        except Exception as e:
            logger.warning(f"Scroll error: {e}")
            break


def extract_comments(page: Page) -> List[Dict[str, Any]]:
    """Extract comments from a Medium article."""
    comments = []
    for el in page.locator("xpath=//pre/ancestor::div[5]").all():
        parent_classes = el.evaluate(
            """(el) => el.parentElement.parentElement.classList.value"""
        )
        if "l" not in parent_classes:
            continue

        comment_data = {
            "references_article": el.locator("p[id^='embedded-quote']").count() > 0,
            "username": "Unknown",
            "text": "",
            "claps": "0",
            "full_html_text": el.inner_text(),
        }

        authors = el.locator("a[href^='/@']").all()
        if authors:
            href = authors[0].get_attribute("href")
            comment_data["username"] = (
                href.split("?")[0].split("/")[1] if href else "Unknown"
            )

        try:
            comment_data["text"] = el.evaluate(
                """(el) => el.firstElementChild.firstElementChild.firstElementChild.lastElementChild.previousElementSibling.innerText"""
            )
            if claps_element := el.locator("div.pw-multi-vote-count").first:
                comment_data["claps"] = claps_element.inner_text(timeout=500) or "0"
        except:
            pass
        try:
            comment_data["full_text"] = el.inner_text()
        except Exception as e:
            logger.warning(f"Failed to extract full text: {e}")
            comment_data["full_text"] = ""
        comments.append(comment_data)
    return comments


def extract_recommendation_urls(page: Page) -> List[str]:
    """Extract recommended article URLs."""
    urls = []
    header = page.locator('h2', has_text="Recommended from Medium").first
    if not header:
        logger.warning("No recommendations found")
        return urls
    
    container = header.locator('xpath=..') # Get parent element using XPath
    if not container:
        logger.warning("No recommendations container found")
        return urls

    articles = container.locator('div[role="link"]').all()
    print(articles)
    for article in articles:
        try:
            url = article.get_attribute("data-href") or ""
            if url:
                urls.append(url)
            else:
                raise Exception("No URL found")
        except Exception as e:
            logger.warning(f"Failed to extract recommendation URL: {e}")
            
    return urls


def extract_metadata_and_comments(page: Page) -> Dict[str, Any]:
    """Extract article metadata and comments."""
    article_data = {
        "title": "Unknown title",
        "author": None,
        "date_published": "Unknown date",
        "date_modified": "Unknown date",
        "description": "No description",
        "publisher": "Unknown publisher",
        "is_free": "Public",
        "claps": "0",
        "comments_count": 0,
        "tags": "",
        "full_text": "",
    }

    # Try to extract from JSON-LD
    if script := page.query_selector('script[type="application/ld+json"]'):
        try:
            json_ld = json.loads(script.inner_text())
            article_data.update(
                {
                    "title": json_ld.get("headline", "Unknown title"),
                    "author": json_ld.get("author", {}).get("name", "Unknown author"),
                    "date_published": json_ld.get("datePublished", "Unknown date"),
                    "date_modified": json_ld.get("dateModified", "Unknown date"),
                    "description": json_ld.get("description", "No description"),
                    "publisher": json_ld.get("publisher", {}).get(
                        "name", "Unknown publisher"
                    ),
                    "is_free": (
                        "Paid"
                        if page.query_selector("article.meteredContent")
                        else "Public"
                    ),
                }
            )
        except (json.JSONDecodeError, TypeError):
            pass

    # Check for paywall indicators
    if page.query_selector('div[aria-label="Post Preview"]') or page.query_selector(
        "div.paywall-upsell-container"
    ):
        article_data["is_free"] = "Member-Only"

    if claps_element := page.query_selector("div.pw-multi-vote-count p"):
        article_data["claps"] = claps_element.inner_text()

    article_data["full_text"] = extract_text(page)
    article_data["tags"] = ",".join(
        tag.inner_text() for tag in page.query_selector_all('a[href*="/tag/"]')
    )

    comments_data = []
    if click_see_all_responses(page):
        scroll_to_load_comments(page)
        comments_data = extract_comments(page)
    article_data["comments_count"] = len(comments_data)
    article_data["comments"] = comments_data

    return article_data


def persist_article_data(session, url_id: int, metadata: Dict[str, Any]) -> bool:
    """Save article metadata and comments to the database."""
    try:
        title = metadata.get("title", "").strip()
        if not title or title == "Unknown title":
            logger.info(f"URL ID {url_id} is not a valid article - No title")
            return False

        article_data = {
            "title": title,
            "author_name": metadata.get("author", "Unknown"),
            "date_published": metadata.get("date_published", ""),
            "date_modified": metadata.get("date_modified", ""),
            "description": metadata.get("description", ""),
            "publisher": metadata.get("publisher", ""),
            "is_free": metadata.get("is_free", ""),
            "claps": metadata.get("claps", ""),
            "comments_count": metadata.get("comments_count", 0),
            "tags": metadata.get("tags", ""),
            "full_article_text": metadata.get("full_text", ""),
        }

        recommendations = metadata.get("recommendations", [])
        for url in recommendations:
            rec_url_id = session.query(URL.id).filter(URL.url == url).scalar()
            if rec_url_id is None:
                url_entry = URL(url=url, sitemap_id=None, found_on_url_id=rec_url_id)
                session.add(url_entry)
                session.commit()
                logger.warning(f"Added recommendation URL: {url}")
            else:
                logger.debug(f"URL already exists: {url}")

        existing_article = (
            session.query(MediumArticle).filter(MediumArticle.url_id == url_id).first()
        )

        if existing_article:
            for key, value in article_data.items():
                setattr(existing_article, key, value)
            article_id = existing_article.id
        else:
            new_article = MediumArticle(url_id=url_id, **article_data)
            session.add(new_article)
            session.commit()
            article_id = new_article.id

        comments_to_save = metadata.get("comments", [])
        if comments_to_save:
            for comment_data in comments_to_save:
                try:
                    filtered_data = {
                        "article_id": article_id,
                        "username": comment_data.get("username", "Unknown"),
                        "text": comment_data.get("text", ""),
                        "claps": comment_data.get("claps", "0"),
                        "references_article": comment_data.get(
                            "references_article", False
                        ),
                        "full_text": comment_data.get("full_html_text", ""),
                    }
                    session.add(Comment(**filtered_data))
                except Exception as e:
                    logger.error(f"Failed to insert comment: {e}")
            session.commit()

        else:
            session.commit()

        logger.info(
            f"Article '{title[:50]}...' has {metadata.get('comments_count', 0)} comments and {len(recommendations)} recommendations"
        )

        logger.debug(f"Saved article data for URL ID {url_id}")
        logger.debug(f"Saved recommendations for URL ID {url_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save article: {e}")
        return False


def setup_signal_handlers(shutdown_event: threading.Event) -> None:
    """Set up signal handlers for graceful shutdown."""

    def handler(sig, frame):
        shutdown_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def verfiy_url_existence(session, page: Page):
    """ Retrieves all URLs from the page and checks if the URL exists in the database. """
    try:
        all_urls = page.query_selector_all("a")
        for url in all_urls:
            if not session.query(URL).filter(URL.url == url.get_attribute("href")).first():
                print(f"URL {url.get_attribute('href')} does not exist in the database.")
                
    except Exception as e:
        logger.error(f"Error verifying URL existence: {e}")
        return False
    
    return True