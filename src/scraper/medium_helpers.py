"""
Helper functions for Medium article scraping.
Contains extraction and database operations to declutter the main script.
"""

import json
import logging
import signal
import threading
from datetime import datetime
from typing import Any, Dict, List, Tuple

from playwright.sync_api import Page
from sqlalchemy import func, select, update

from database.database import URL, Author, MediumArticle

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_random_urls(session, count: int = 10) -> List[Tuple[int, str]]:
    """
    Fetch random URLs from the database.

    Args:
        session: Database session
        count: Number of URLs to retrieve

    Returns:
        List of tuples containing (url_id, url)
    """
    return session.query(URL.id, URL.url).order_by(func.random()).limit(count).all()


def update_url_status(session, url_id: int, success: bool):
    """
    Update the URL's last_crawled timestamp and crawl_status.

    Args:
        session: Database session
        url_id: ID of the URL to update
        success: Whether the crawl was successful
    """
    try:
        url = session.query(URL).filter(URL.id == url_id).first()
        if url:
            url.last_crawled = datetime.now()
            url.crawl_status = "Successful" if success else "Failed"
            session.commit()
            logger.info(
                f"Updated URL {url_id} with status: {'Successful' if success else 'Failed'}"
            )
    except Exception as e:
        session.rollback()
        logger.error(f"Database error for URL {url_id}: {e}")


def extract_text(page: Page) -> str:
    """
    Extract full article text with better paragraph selection.

    Args:
        page: Playwright page object

    Returns:
        Extracted article text as string
    """
    paragraphs = page.query_selector_all("article p[data-selectable-paragraph]")
    if not paragraphs:
        logger.debug("No paragraphs found with data-selectable-paragraph attribute")
        # Fall back to generic paragraph selection
        paragraphs = page.query_selector_all("article p")
        if not paragraphs:
            logger.debug("No paragraphs found for text extraction")
            return ""

    text_parts = []
    for p in paragraphs:
        try:
            if text := p.inner_text():
                text_parts.append(text)
        except Exception as e:
            logger.warning(f"Failed to extract text from paragraph: {str(e)}")

    return "\n".join(text_parts)


def extract_metadata(page: Page) -> Dict[str, Any]:
    """
    Extract article metadata from JSON-LD and page elements.

    Args:
        page: Playwright page object

    Returns:
        Dictionary containing article metadata
    """
    article_data = {
        "title": "Unknown title",
        "author": None,  # Changed to match what save_article expects
        "date_published": "Unknown date",
        "date_modified": "Unknown date",
        "description": "No description",
        "publisher": "Unknown publisher",
        "is_free": "Public",  # Default to Public
        "claps": "0",
        "comments_count": 0,
        "tags": "",
        "full_text": "",  # Changed to match what save_article expects
    }

    # Extract JSON-LD data
    script = page.query_selector('script[type="application/ld+json"]')
    if script:
        try:
            json_ld = json.loads(script.inner_text())
            article_data["title"] = json_ld.get("headline", "Unknown title")
            article_data["author"] = json_ld.get("author", {}).get(
                "name", "Unknown author"
            )
            article_data["date_published"] = json_ld.get(
                "datePublished", "Unknown date"
            )
            article_data["date_modified"] = json_ld.get("dateModified", "Unknown date")
            article_data["description"] = json_ld.get("description", "No description")
            article_data["publisher"] = json_ld.get("publisher", {}).get(
                "name", "Unknown publisher"
            )

            # Correct classification for is_free
            is_accessible = json_ld.get("isAccessibleForFree")
            if is_accessible is True:
                article_data["is_free"] = "Paid"
            elif is_accessible is False:
                article_data["is_free"] = "Member-Only"
            else:
                article_data["is_free"] = "Public"

        except json.JSONDecodeError:
            logger.error("Failed to parse JSON-LD data")

    # Look for the member-only or paywall indicator as a fallback
    try:
        member_content = page.query_selector('div[aria-label="Post Preview"]')
        if member_content:
            article_data["is_free"] = "Member-Only"

        paywall = page.query_selector("div.paywall-upsell-container")
        if paywall:
            article_data["is_free"] = "Paid"
    except Exception:
        pass

    # Extract claps
    claps_element = page.query_selector("div.pw-multi-vote-count p")
    if claps_element:
        article_data["claps"] = claps_element.inner_text()

    # Extract article text using improved method
    article_data["full_text"] = extract_text(page)

    # Extract tags
    tags = page.query_selector_all('a[href*="/tag/"]')
    article_data["tags"] = ",".join([tag.inner_text() for tag in tags]) if tags else ""

    return article_data


def save_article(session, url_id: int, metadata: Dict[str, Any]) -> bool:
    """
    Save article metadata to database (synchronous version)

    Args:
        session: SQLAlchemy session
        url_id: URL ID in database
        metadata: Dictionary with article metadata

    Returns:
        True if successful, False otherwise
    """
    try:
        # Handle author (create if not exists)
        author = None
        if metadata.get("author"):
            author = session.query(Author).filter_by(name=metadata["author"]).first()
            if not author:
                author = Author(name=metadata["author"])
                session.add(author)
                session.flush()  # Get ID without committing

        # Check if article already exists
        existing = (
            session.query(MediumArticle).filter(MediumArticle.url_id == url_id).first()
        )

        if existing:
            # Update existing record
            existing.title = metadata.get("title", "")
            existing.author_id = author.id if author else None
            existing.date_published = metadata.get("date_published", "")
            existing.date_modified = metadata.get("date_modified", "")
            existing.description = metadata.get("description", "")
            existing.publisher = metadata.get("publisher", "")
            existing.is_free = metadata.get("is_free", "")
            existing.claps = metadata.get("claps", "")
            existing.comments_count = metadata.get("comments_count", 0)
            existing.tags = metadata.get("tags", "")
            existing.full_article_text = metadata.get("full_text", "")
            logger.debug(f"Updated existing article for URL ID {url_id}")
        else:
            # Create article
            article = MediumArticle(
                url_id=url_id,
                title=metadata.get("title", ""),
                author_id=author.id if author else None,
                date_published=metadata.get("date_published", ""),
                date_modified=metadata.get("date_modified", ""),
                description=metadata.get("description", ""),
                publisher=metadata.get("publisher", ""),
                is_free=metadata.get("is_free", ""),
                claps=metadata.get("claps", ""),
                comments_count=metadata.get("comments_count", 0),
                tags=metadata.get("tags", ""),
                full_article_text=metadata.get("full_text", ""),
            )

            session.add(article)
            logger.debug(f"Created new article for URL ID {url_id}")

        session.commit()
        logger.info(f"Saved article data for URL ID {url_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save article: {e}")
        return False


def setup_signal_handlers(shutdown_event: threading.Event) -> None:
    """
    Set up signal handlers for graceful shutdown.

    Args:
        shutdown_event: Event to set when shutdown is triggered
    """
    signal.signal(signal.SIGINT, lambda sig, frame: shutdown_event.set())
    signal.signal(signal.SIGTERM, lambda sig, frame: shutdown_event.set())
