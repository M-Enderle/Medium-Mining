import asyncio
import json
import logging
import random
from datetime import datetime

from playwright.async_api import BrowserContext, Page, async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from database.database import (
    DATABASE_URL,
    URL,
    Base,
    Comment,
    MediumArticle,
    setup_database,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
VIEWPORT = {"width": 414, "height": 896}
HEADERS = {"Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"}

async_engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)


async def disable_bloating(page: Page) -> None:
    """Disable loading of images and unnecessary resources."""
    await page.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.resource_type in ("image", "stylesheet", "font")
            else route.continue_()
        ),
    )


async def close_signup_popup(page: Page) -> None:
    """Close the signup popup if it exists."""
    for button in await page.locator('button[aria-label="close"]').all():
        if await button.is_visible():
            await button.click()
            break


async def extract_metadata(page: Page, article_data: dict) -> None:
    """Extract article metadata from JSON-LD."""
    if script := await page.query_selector('script[type="application/ld+json"]'):
        try:
            json_ld = json.loads(await script.inner_text())
            article_data["title"] = json_ld.get("headline", "Unknown title")
            article_data["author_name"] = json_ld.get("author", {}).get(
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
            article_data["is_free"] = str(json_ld.get("isAccessibleForFree", "Unknown"))
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON-LD data")

    claps_element = await page.query_selector("div.pw-multi-vote-count p")
    article_data["claps"] = await claps_element.inner_text() if claps_element else "0"


async def extract_tags(page: Page, article_data: dict) -> None:
    """Extract article tags."""
    tags = await page.query_selector_all('a[href*="/tag/"]')
    article_data["tags"] = (
        ",".join([await tag.inner_text() for tag in tags]) if tags else ""
    )


async def extract_text(page: Page, article_data: dict) -> None:
    """Extract full article text."""
    paragraphs = await page.query_selector_all("article p[data-selectable-paragraph]")
    if not paragraphs:
        logging.debug("No paragraphs found for text extraction")
        article_data["full_article_text"] = ""
        return

    text_parts = []
    for p in paragraphs:
        try:
            if text := await p.inner_text():
                text_parts.append(text)
        except Exception as e:
            logging.warning(f"Failed to extract text from paragraph: {str(e)}")
    article_data["full_article_text"] = "\n".join(text_parts)


async def extract_comments(page: Page, article_data: dict) -> None:
    """Extract comments."""
    comments_data = []
    for el in await page.locator("xpath=//pre/ancestor::div[5]").all():
        parent_classes = await el.evaluate(
            """(el) => el.parentElement.parentElement.classList.value"""
        )
        if "l" not in parent_classes:
            continue

        comment_data = {}

        try:
            comment_data["references_article"] = (
                await el.locator("p[id^='embedded-quote']").count()
            ) > 0
        except Exception:
            comment_data["references_article"] = False

        authors = await el.locator("a[href^='/@']").all()
        comment_data["username"] = (
            await authors[0].get_attribute("href").split("?")[0].split("/")[1]
            if authors
            else "Unknown"
        )

        try:
            comment_data["text"] = await el.evaluate(
                """(el) => el.firstElementChild.firstElementChild.firstElementChild.lastElementChild.previousElementSibling.innerText"""
            )
        except Exception:
            comment_data["text"] = ""

        try:
            claps_element = await el.locator("div.pw-multi-vote-count").first
            comment_data["claps"] = await claps_element.inner_text(timeout=100)
        except Exception:
            comment_data["claps"] = "0"

        comment_data["full_html_text"] = await el.inner_text()
        comments_data.append(comment_data)

    article_data["comments"] = comments_data
    article_data["comments_count"] = len(comments_data)


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
            await page.wait_for_load_state("load", timeout=15000)
            if html == (new_html := await page.content()):
                break
            html = new_html
        except Exception as e:
            logging.warning(f"Failed during scrolling: {e}")


async def scrape_article(
    url: str, context: BrowserContext, semaphore: asyncio.Semaphore
) -> dict | None:
    """Scrapes a single article and returns a dictionary with the data."""
    page = None
    try:
        async with semaphore:
            page = await context.new_page()
            await disable_bloating(page)
            await page.goto(url, timeout=15000)
            await page.wait_for_timeout(random.randint(500, 10000))
            await page.wait_for_load_state("load", timeout=15000)
            await close_signup_popup(page)

            article_data = {}
            await extract_metadata(page, article_data)
            await extract_tags(page, article_data)
            await extract_text(page, article_data)

            if not article_data.get("title"):
                logging.warning("No title found, skipping article")
                return None

            await _click_see_all_responses(page)
            await _scroll_to_load_comments(page)
            await extract_comments(page, article_data)

            return article_data

    except Exception as e:
        logging.error(f"Error scraping {url}: {str(e)}")
        return None

    finally:
        if page:
            await page.close()


async def insert_article_data(article_data: dict, db_lock: asyncio.Lock):
    """Inserts the scraped article data into the database."""
    async with AsyncSessionLocal() as session:
        async with db_lock:
            try:
                url_obj = await session.get(URL, article_data["url"])
                if not url_obj:
                    logging.warning(f"URL {article_data['url']} not found.")
                    return

                article = MediumArticle(
                    article_url=url_obj,
                    title=article_data.get("title", "Unknown Title"),
                    author_name=article_data.get("author_name", "Unknown Author"),
                    date_published=article_data.get("date_published", "Unknown Date"),
                    date_modified=article_data.get("date_modified", "Unknown Date"),
                    description=article_data.get("description", ""),
                    publisher=article_data.get("publisher", "Unknown Publisher"),
                    is_free=article_data.get("is_free", "Unknown"),
                    claps=article_data.get("claps", "0"),
                    comments_count=article_data.get("comments_count", 0),
                    tags=article_data.get("tags", ""),
                    full_article_text=article_data.get("full_article_text", ""),
                )
                await session.add(article)
                await session.flush()

                for comment_data in article_data.get("comments", []):
                    comment = Comment(
                        article_id=article.id,
                        username=comment_data.get("username", "Unknown User"),
                        text=comment_data.get("text", ""),
                        claps=comment_data.get("claps", "0"),
                        full_html_text=comment_data.get("full_html_text", ""),
                        references_article=comment_data.get(
                            "references_article", False
                        ),
                    )
                    await session.add(comment)

                url_obj.crawl_status = "Success"
                url_obj.last_crawled = datetime.now()

                await session.commit()
                logging.info(f"Successfully inserted data for: {url_obj.url}")

            except Exception as e:
                await session.rollback()
                logging.exception(
                    f"Error inserting data for {article_data.get('url')}: {e}"
                )
                if "url_obj" in locals():
                    url_obj.crawl_status = f"Failed: {str(e)}"
                    url_obj.last_crawled = datetime.now()
                    await session.commit()


async def main():
    """Main function to scrape articles in parallel."""

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=USER_AGENT, viewport=VIEWPORT, extra_http_headers=HEADERS
        )
        _ = await context.new_page()

        semaphore = asyncio.Semaphore(5)
        db_lock = asyncio.Lock()

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(URL.url).where(URL.last_crawled == None).limit(100)
                )
                urls = [url[0] for url in result.all()]
                logging.info(f"Found {len(urls)} URLs to scrape.")

            scraping_tasks = []
            for url in urls:
                scraping_tasks.append(
                    asyncio.create_task(scrape_article(url, context, semaphore))
                )

            scraped_articles = await asyncio.gather(*scraping_tasks)

            insertion_tasks = []
            for i, article_data in enumerate(scraped_articles):
                if article_data:
                    article_data["url"] = urls[i]
                    insertion_tasks.append(insert_article_data(article_data, db_lock))

            await asyncio.gather(*insertion_tasks)

        except Exception as e:
            logging.exception(f"An error occurred in main: {e}")

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
