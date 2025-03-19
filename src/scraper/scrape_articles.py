import asyncio
from sqlalchemy import func
from sqlalchemy.orm import Session
from database.database import (
    get_session,
    URL,
    MediumArticle,
    Comment,
    setup_database
)
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, BrowserContext
import json
import logging
from datetime import datetime
import re

# Configure logging (keeping it simple for now)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    # Remove the file handler to prevent issues during shutdown.  Log to console only.
    # handlers=[logging.FileHandler("sitemap_scraper.log"), logging.StreamHandler()],
    handlers=[logging.StreamHandler()],
)

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
VIEWPORT = {"width": 414, "height": 896}
HEADERS = {"Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"}


async def disable_bloating(page: Page) -> None:
    """Disable loading of images and unnecessary resources."""
    await page.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("image", "stylesheet", "font")
        else route.continue_(),
    )


async def close_signup_popup(page: Page) -> None:
    """Close the signup popup if it exists."""
    for button in await page.locator('button[aria-label="close"]').all():
        if await button.is_visible():
            await button.click()
            break


async def extract_metadata(page: Page, article: MediumArticle) -> None:
    """Extract article metadata from JSON-LD and update the MediumArticle object."""
    if script := await page.query_selector('script[type="application/ld+json"]'):
        try:
            json_ld = json.loads(await script.inner_text())
            article.title = json_ld.get("headline", "Unknown title")
            article.author_name = json_ld.get("author", {}).get("name", "Unknown author")
            article.date_published = json_ld.get("datePublished", "Unknown date")
            article.date_modified = json_ld.get("dateModified", "Unknown date")
            article.description = json_ld.get("description", "No description")
            article.publisher = json_ld.get("publisher", {}).get("name", "Unknown publisher")
            article.is_free = str(json_ld.get("isAccessibleForFree", "Unknown"))
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON-LD data")

    claps_element = await page.query_selector("div.pw-multi-vote-count p")
    article.claps = await claps_element.inner_text() if claps_element else "0"


async def extract_tags(page: Page, article: MediumArticle) -> None:
    """Extract article tags and update the MediumArticle object."""
    tags = await page.query_selector_all('a[href*="/tag/"]')
    article.tags = ",".join([await tag.inner_text() for tag in tags]) if tags else ""


async def extract_text(page: Page, article: MediumArticle) -> None:
    """Extract full article text and update the MediumArticle object."""
    paragraphs = await page.query_selector_all("article p[data-selectable-paragraph]")
    if not paragraphs:
        logging.debug("No paragraphs found for text extraction")
        article.full_article_text = ""
        return

    text_parts = []
    for p in paragraphs:
        try:
            if text := await p.inner_text():
                text_parts.append(text)
        except Exception as e:
            logging.warning(f"Failed to extract text from paragraph: {str(e)}")
    article.full_article_text = "\n".join(text_parts)


async def extract_comments(page: Page, article: MediumArticle, session: Session) -> None:
    """Extract comments and add them as Comment objects to the session."""
    for el in await page.locator('xpath=//pre/ancestor::div[5]').all():
        parent_classes = await el.evaluate(
            """(el) => el.parentElement.parentElement.classList.value"""
        )
        if "l" not in parent_classes:
            continue

        comment = Comment(article=article)

        try:
            comment.references_article = (
                await el.locator("p[id^='embedded-quote']").count()
            ) > 0
        except Exception:
            comment.references_article = False

        # Extract author
        authors = await el.locator("a[href^='/@']").all()
        comment.username = (
            await authors[0].get_attribute("href").split("?")[0].split("/")[1]
            if authors
            else "Unknown"
        )

        # Extract comment text (handle potential absence)
        try:
            comment.text = await el.evaluate(
                """(el) => el.firstElementChild.firstElementChild.firstElementChild.lastElementChild.previousElementSibling.innerText"""
            )
        except Exception:
            comment.text = ""

        try:
            claps_element = await el.locator("div.pw-multi-vote-count").first
            comment.claps = await claps_element.inner_text(timeout=100)
        except Exception:
            comment.claps = "0"

        comment.full_html_text = await el.inner_text()

        session.add(comment)


async def _click_see_all_responses(page: Page) -> None:
    """Click 'See all responses' button."""
    if button := await page.query_selector('button:has-text("See all responses")'):
        try:
            await button.click(timeout=15000)
            await page.wait_for_load_state("load", timeout=15000)
        except Exception as e:
             logging.warning(f"Failed to click 'See all responses': {e}")


async def _scroll_to_load_comments(page: Page) -> None:
    """Scroll to load all comments."""
    html = await page.content()
    for _ in range(100):
        try:
            await page.evaluate(
                """document.querySelector('div[role="dialog"]')?.lastElementChild.firstElementChild.scrollBy(0, 200000)"""
            )
            await page.wait_for_timeout(500)
            await page.wait_for_load_state('load', timeout=15000)
            if html == (new_html := await page.content()):
                break
            html = new_html
        except Exception as e:
            logging.warning(f"Failed during scrolling: {e}")

async def scrape_article(url: URL, context: BrowserContext, session: Session) -> None:
    """Scrape a Medium article and its comments, saving data to the database."""
    page = None
    article = None  # Initialize article here
    try:
        page = await context.new_page()
        await disable_bloating(page)

        await page.goto(url.url, timeout=60000)
        await page.wait_for_load_state("load", timeout=30000)

        await close_signup_popup(page)

        article = MediumArticle(article_url=url)
        await extract_metadata(page, article)
        await extract_tags(page, article)
        await extract_text(page, article)

        session.add(article)
        session.flush()  # Get the article ID

        # Load and extract comments
        await _click_see_all_responses(page)
        await _scroll_to_load_comments(page)
        await extract_comments(page, article, session)
        article.comments_count = len(article.comments)
        article.last_crawled = datetime.now()
        article.crawl_status = "Success"


        logging.info(f"Successfully scraped: {url.url}")


    except Exception as e:
        logging.error(f"Error scraping {url.url}: {str(e)}")
        if article:  # Only update if article was created
            article.crawl_status = "Failed"
        session.rollback()
    finally:
        if page:
            await page.close()
        # Commit *after* closing the page, but *within* the try/finally.
        if article and article.crawl_status == "Success":
            try:
                session.commit()
            except Exception as e:
                logging.error(f"Error committing to database: {e}")
                session.rollback()


async def main():
    """Main function to scrape articles in parallel."""
    session = None  # Initialize session to None
    for i in range(100):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context(
                    user_agent=USER_AGENT, viewport=VIEWPORT, extra_http_headers=HEADERS
                )
                session = get_session()  # Get session *inside* the async context

                urls = session.query(URL).filter(URL.crawled==False).filter(URL.priority==1.0).limit(10).all()

                if not urls:
                    logging.info("No URLs found in the database.")
                    return

                tasks = [scrape_article(url, context, session) for url in urls]
                await asyncio.gather(*tasks)  # Ensure all scraping tasks complete

                # Mark URLs as crawled
                for url in urls:
                    url.crawled = True
                    session.add(url)
                session.commit()
                logging.info("All URLs marked as crawled.")

                await context.close()
                await browser.close()

        except Exception as e:
            logging.exception(f"An error occurred in main: {e}")  # Use logging.exception
        finally:
            # Make *absolutely* sure the session is closed, even if errors occur.
            if session:
                session.close()


if __name__ == "__main__":
    setup_database()
    asyncio.run(main())