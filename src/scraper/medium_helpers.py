"""
Helper functions for Medium article scraping.
Contains extraction and database operations to declutter the main script.
"""

import json
import asyncio
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime

from playwright.async_api import Page
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import URL, MediumArticle

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global lock for database operations
db_lock = asyncio.Lock()

async def get_random_urls(session: AsyncSession, count: int = 10) -> List[Tuple[int, str]]:
    """Fetch random URLs from the database."""
    result = await session.execute(select(URL.id, URL.url).order_by(func.random()).limit(count))
    return [(row[0], row[1]) for row in result]

async def update_url_status(session: AsyncSession, url_id: int, success: bool):
    """Update the URL's last_crawled timestamp and crawl_status."""
    async with db_lock:
        try:
            await session.execute(update(URL).where(URL.id == url_id)
                                .values(last_crawled=datetime.now(), 
                                        crawl_status="Successful" if success else "Failed"))
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"DB error for {url_id}: {e}")

async def extract_text(page: Page) -> str:
    """Extract full article text with better paragraph selection."""
    paragraphs = await page.query_selector_all("article p[data-selectable-paragraph]")
    if not paragraphs:
        logger.debug("No paragraphs found with data-selectable-paragraph attribute")
        # Fall back to generic paragraph selection
        paragraphs = await page.query_selector_all("article p")
        if not paragraphs:
            logger.debug("No paragraphs found for text extraction")
            return ""
    
    text_parts = []
    for p in paragraphs:
        try:
            if text := await p.inner_text():
                text_parts.append(text)
        except Exception as e:
            logger.warning(f"Failed to extract text from paragraph: {str(e)}")
    
    return "\n".join(text_parts)

async def extract_metadata(page: Page) -> Dict[str, Any]:
    """Extract article metadata from JSON-LD and page elements."""
    article_data = {
        "title": "Unknown title",
        "author_name": "Unknown author",
        "date_published": "Unknown date",
        "date_modified": "Unknown date",
        "description": "No description",
        "publisher": "Unknown publisher",
        "is_free": "Public",  # Default to Public
        "claps": "0",
        "comments_count": 0,
        "tags": "",
        "full_article_text": ""
    }
    
    # Extract JSON-LD data
    if script := await page.query_selector('script[type="application/ld+json"]'):
        try:
            json_ld = json.loads(await script.inner_text())
            article_data["title"] = json_ld.get("headline", "Unknown title")
            article_data["author_name"] = json_ld.get("author", {}).get("name", "Unknown author")
            article_data["date_published"] = json_ld.get("datePublished", "Unknown date")
            article_data["date_modified"] = json_ld.get("dateModified", "Unknown date")
            article_data["description"] = json_ld.get("description", "No description")
            article_data["publisher"] = json_ld.get("publisher", {}).get("name", "Unknown publisher")
            
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
        member_content = await page.query_selector('div[aria-label="Post Preview"]')
        if member_content:
            article_data["is_free"] = "Member-Only"
            
        paywall = await page.query_selector('div.paywall-upsell-container')
        if paywall:
            article_data["is_free"] = "Paid"
    except Exception:
        pass
    
    # Extract claps
    claps_element = await page.query_selector("div.pw-multi-vote-count p")
    if claps_element:
        article_data["claps"] = await claps_element.inner_text()
    
    # Extract article text using improved method
    article_data["full_article_text"] = await extract_text(page)
    
    # Extract tags
    tags = await page.query_selector_all('a[href*="/tag/"]')
    article_data["tags"] = ",".join([await tag.inner_text() for tag in tags]) if tags else ""
    
    return article_data

async def save_article(session: AsyncSession, url_id: int, metadata: Dict[str, Any]) -> None:
    """Save article metadata to database."""
    async with db_lock:
        try:
            # Check if article already exists
            stmt = select(MediumArticle).where(MediumArticle.url_id == url_id)
            result = await session.execute(stmt)
            existing = result.scalars().first()
            
            if existing:
                # Update existing record
                for key, value in metadata.items():
                    setattr(existing, key, value)
            else:
                # Create new record
                article = MediumArticle(
                    url_id=url_id,
                    **metadata
                )
                session.add(article)
            
            await session.commit()
            print(f"Saved article data for URL ID {url_id}")
        except Exception as e:
            await session.rollback()
            print(f"Error saving article data for URL ID {url_id}: {e}")

def setup_signal_handlers(shutdown_event: asyncio.Event) -> None:
    """Set up signal handlers for graceful shutdown."""
    loop = asyncio.get_event_loop()
    for sig in (2, 15):  # SIGINT, SIGTERM
        loop.add_signal_handler(sig, lambda: shutdown_event.set())
