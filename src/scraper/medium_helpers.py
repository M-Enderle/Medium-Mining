"""Helper functions for Medium article scraping."""

import json
import logging
import signal
import threading
from datetime import datetime
from typing import Any, Dict, List, Tuple

from playwright.sync_api import Page
from sqlalchemy import func

from database.database import URL, Author, MediumArticle

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def fetch_random_urls(session, count: int = 10) -> List[Tuple[int, str]]:
    """Fetch random URLs from the database."""
    return session.query(URL.id, URL.url).order_by(func.random()).limit(count).all()


def update_url_status(session, url_id: int, success: bool):
    """Update the URL's last_crawled timestamp and crawl_status."""
    try:
        url = session.query(URL).filter(URL.id == url_id).first()
        if url:
            url.last_crawled = datetime.now()
            url.crawl_status = "Successful" if success else "Failed"
            session.commit()
            logger.info(
                f"Updated URL {url_id} status: {'Successful' if success else 'Failed'}"
            )
    except Exception as e:
        session.rollback()
        logger.error(f"DB error for URL {url_id}: {e}")


def extract_text(page: Page) -> str:
    """Extract full article text with better paragraph selection."""
    paragraphs = page.query_selector_all(
        "article p[data-selectable-paragraph]"
    ) or page.query_selector_all("article p")
    if not paragraphs:
        return ""

    text_parts = []
    for p in paragraphs:
        try:
            if text := p.inner_text():
                text_parts.append(text)
        except Exception as e:
            logger.warning(f"Text extraction error: {e}")

    return "\n".join(text_parts)


def click_see_all_responses(page: Page) -> bool:
    """Click 'See all responses' button to load comments section."""
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
            # Scroll the comments dialog
            page.evaluate(
                """() => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (dialog) dialog.lastElementChild.firstElementChild.scrollBy(0, 20000);
            }"""
            )
            page.wait_for_timeout(500)
            page.wait_for_load_state("load", timeout=5000)

            new_html = page.content()
            if html == new_html:  # No new content loaded
                break
            html = new_html
        except Exception as e:
            logger.warning(f"Scroll error: {e}")
            break


def extract_comments(page: Page) -> List[Dict[str, Any]]:
    """Extract comments from a Medium article."""
    comments = []

    try:
        comment_elements = page.locator("xpath=//pre/ancestor::div[5]").all()

        for el in comment_elements:
            # Skip non-comments
            parent_classes = el.evaluate(
                """(el) => el.parentElement.parentElement.classList.value"""
            )
            if "l" not in parent_classes:
                continue

            comment_data = {
                "references_article": False,
                "username": "Unknown",
                "text": "",
                "claps": "0",
                "full_html_text": el.inner_text(),
            }

            # Check if comment references article
            try:
                comment_data["references_article"] = (
                    el.locator("p[id^='embedded-quote']").count() > 0
                )
            except:
                pass

            # Get author username
            try:
                authors = el.locator("a[href^='/@']").all()
                if authors:
                    href = authors[0].get_attribute("href")
                    comment_data["username"] = (
                        href.split("?")[0].split("/")[1] if href else "Unknown"
                    )
            except:
                pass

            # Get comment text and claps
            try:
                comment_data["text"] = el.evaluate(
                    """(el) => el.firstElementChild.firstElementChild.firstElementChild.lastElementChild.previousElementSibling.innerText"""
                )

                claps_element = el.locator("div.pw-multi-vote-count").first
                if claps_element:
                    comment_data["claps"] = claps_element.inner_text(timeout=500) or "0"
            except:
                pass

            comments.append(comment_data)

    except Exception as e:
        logger.error(f"Error extracting comments: {e}")

    return comments


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

    # Extract JSON-LD data
    try:
        script = page.query_selector('script[type="application/ld+json"]')
        if script and (json_ld := json.loads(script.inner_text())):
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
                }
            )

            # Handle accessibility/paywall
            is_accessible = json_ld.get("isAccessibleForFree")
            if is_accessible is True:
                article_data["is_free"] = "Paid"
            elif is_accessible is False:
                article_data["is_free"] = "Member-Only"
    except:
        pass

    # Check for member/paywall indicators
    try:
        if page.query_selector('div[aria-label="Post Preview"]'):
            article_data["is_free"] = "Member-Only"
        if page.query_selector("div.paywall-upsell-container"):
            article_data["is_free"] = "Paid"
    except:
        pass

    # Get claps
    if claps_element := page.query_selector("div.pw-multi-vote-count p"):
        article_data["claps"] = claps_element.inner_text()

    # Get article text
    article_data["full_text"] = extract_text(page)

    # Get tags
    if tags := page.query_selector_all('a[href*="/tag/"]'):
        article_data["tags"] = ",".join(tag.inner_text() for tag in tags)

    # Extract comments
    comments_data = []
    try:
        if click_see_all_responses(page):
            scroll_to_load_comments(page)
            comments_data = extract_comments(page)

            if comments_data:
                logger.info(f"Extracted {len(comments_data)} comments")
                if comments_data:
                    first = comments_data[0]
                    sample = first["text"][:100] + (
                        "..." if len(first["text"]) > 100 else ""
                    )
                    logger.info(f"First comment: {first['username']} - '{sample}'")
            else:
                logger.info("No comments found for this article")
    except Exception as e:
        logger.warning(f"Comment extraction error: {e}")

    article_data["comments"] = comments_data
    article_data["comments_count"] = len(comments_data)

    return article_data


def persist_article_data(session, url_id: int, metadata: Dict[str, Any]) -> bool:
    """Save article metadata to database."""
    try:
        # Handle author
        author = None
        if metadata.get("author"):
            author = session.query(Author).filter_by(name=metadata["author"]).first()
            if not author:
                author = Author(name=metadata["author"])
                session.add(author)
                session.flush()

        # Check if article exists
        existing = (
            session.query(MediumArticle).filter(MediumArticle.url_id == url_id).first()
        )
        article_data = {
            "title": metadata.get("title", ""),
            "author_id": author.id if author else None,
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

        if existing:
            # Update existing record
            for key, value in article_data.items():
                setattr(existing, key, value)
        else:
            # Create new record
            article = MediumArticle(url_id=url_id, **article_data)
            session.add(article)

        # Save comments if model exists and comments are available
        if metadata.get("comments"):
            try:
                # Try to import Comment class
                from database.database import Comment

                has_comment_model = True

                # Try to discover available fields in Comment model
                valid_fields = []
                try:
                    # Inspect the Comment model's columns
                    dummy = Comment()
                    if hasattr(dummy, "__table__") and hasattr(
                        dummy.__table__, "columns"
                    ):
                        valid_fields = [col.name for col in dummy.__table__.columns]
                    else:
                        # Alternative approach
                        valid_fields = [
                            "article_id",
                            "username",
                            "text",
                            "references_article",
                        ]
                except:
                    # Fallback to basic fields that should exist
                    valid_fields = [
                        "article_id",
                        "username",
                        "text",
                        "references_article",
                    ]

                logger.debug(f"Valid Comment fields: {valid_fields}")
            except (ImportError, AttributeError):
                has_comment_model = False
                logger.warning("Comment model not found, skipping comment storage")

            if has_comment_model:
                article_id = existing.id if existing else None
                # Need to flush to get article ID if it's a new article
                if not article_id:
                    session.flush()
                    article_id = article.id

                comments_saved = 0
                for comment_data in metadata["comments"]:
                    try:
                        # Start with required fields
                        filtered_data = {"article_id": article_id}

                        # Only add fields that exist in the model
                        for field, value in {
                            "username": comment_data.get("username", "Unknown"),
                            "text": comment_data.get("text", ""),
                            "references_article": comment_data.get(
                                "references_article", False
                            ),
                        }.items():
                            if field in valid_fields:
                                filtered_data[field] = value

                        # Special handling for claps/likes field
                        clap_value = comment_data.get("claps", "0")
                        if "claps" in valid_fields:
                            filtered_data["claps"] = clap_value
                        elif "likes" in valid_fields:
                            filtered_data["likes"] = clap_value

                        # Create and add comment
                        comment = Comment(**filtered_data)
                        session.add(comment)
                        comments_saved += 1
                    except Exception as e:
                        logger.warning(f"Failed to create comment: {e}")

                logger.info(
                    f"Successfully saved {comments_saved} of {len(metadata['comments'])} comments"
                )

        session.commit()
        logger.info(f"Saved article data for URL ID {url_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save article: {e}")
        return False


def setup_signal_handlers(shutdown_event: threading.Event) -> None:
    """Set up signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, lambda sig, frame: shutdown_event.set())
    signal.signal(signal.SIGTERM, lambda sig, frame: shutdown_event.set())
