import asyncio
from database.database import get_session, URL, MediumArticle, Comment, Author
from typing import List, Dict
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import json
import logging
from sqlalchemy import func

# Configure logging to file and console in 2 lines
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('sitemap_scraper.log'), logging.StreamHandler()])

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
VIEWPORT = {"width": 414, "height": 896}
HEADERS = {"Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"}

async def disable_bloating(page: Page) -> None:
    """Disable loading of images and recaptcha."""
    await page.route("**/*", lambda route: route.abort()
           if route.request.resource_type == "image"
           else route.continue_()
          )
    await page.route(
        "**/*",
        lambda route: route.abort()
        if "https://www.gstatic.com" in route.request.url
        else route.continue_(),
    )

async def extract_metadata(page: Page) -> Dict[str, str]:
    """Extract article metadata from JSON-LD."""
    metadata = {}
    if script := await page.query_selector('script[type="application/ld+json"]'):
        try:
            json_ld = json.loads(await script.inner_text())
            metadata.update({
                "title": json_ld.get("headline", "Unknown title"),
                "author_name": json_ld.get("author", {}).get("name", "Unknown author"),
                "date_published": json_ld.get("datePublished", "Unknown date"),
                "date_modified": json_ld.get("dateModified", "Unknown date"),
                "description": json_ld.get("description", "No description"),
                "publisher": json_ld.get("publisher", {}).get("name", "Unknown publisher"),
                "is_free": str(json_ld.get("isAccessibleForFree", "Unknown"))
            })
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON-LD data")
    claps_element = await page.query_selector('div.pw-multi-vote-count p')
    metadata["claps"] = await claps_element.inner_text() if claps_element else "0"
    return metadata

async def extract_tags(page: Page) -> List[str]:
    """Extract article tags."""
    tags = await page.query_selector_all('a[href*="/tag/"]')
    return [await tag.inner_text() for tag in tags] if tags else []

async def extract_text(page: Page) -> str:
    """Extract full article text with robust handling."""
    paragraphs = await page.query_selector_all('article p[data-selectable-paragraph]')
    if not paragraphs:
        logging.debug("No paragraphs found for text extraction")
        return ""
    text_parts = []
    for p in paragraphs:
        try:
            text = await p.inner_text()
            if text:  # Only append non-None, non-empty strings
                text_parts.append(text)
        except Exception as e:
            logging.warning(f"Failed to extract text from paragraph: {str(e)}")
    return "\n".join(text_parts) if text_parts else ""

async def _extract_comments(page: Page) -> List[Dict[str, str]]:
    """Extract unique comments from the page."""
    comments, seen = [], set()
    for comment in await page.query_selector_all('div.bh.dw') or []:
        user_elem = await comment.query_selector('a[href*="medium.com/@"]')
        text_elem = await comment.query_selector('pre.rk')
        if not text_elem:
            continue
        text = (await text_elem.inner_text()).strip()
        user_url = (await user_elem.get_attribute('href')).split('?')[0] if user_elem else "Unknown URL"
        if (user_url, text) in seen:
            continue
        seen.add((user_url, text))
        comments.append({
            "user_url": user_url,
            "date": await (await comment.query_selector('p.du')).inner_text() if await comment.query_selector('p.du') else "Unknown date",
            "text": text,
            "claps": await (await comment.query_selector('div.pw-multi-vote-count p')).inner_text() if await comment.query_selector('div.pw-multi-vote-count p') else "0"
        })
    return comments

async def _click_see_all_responses(page: Page) -> None:
    """Click 'See all responses' to load comments."""
    if button := await page.query_selector('button:has-text("See all responses")'):
        await button.click(timeout=15000)
        await page.wait_for_load_state("networkidle", timeout=15000)

async def _scroll_to_load_comments(page: Page) -> None:
    """Scroll to load all comments, up to 5 iterations."""
    html = await page.content()
    for _ in range(5):
        await page.evaluate('document.getElementsByClassName("uj gh")[0]?.scrollBy(0, 10000)')
        await page.wait_for_timeout(1000)
        if html == (new_html := await page.content()):
            break
        html = new_html

async def scrape_article(url: URL, context: BrowserContext, session) -> None:
    """Scrape a Medium article and its comments."""
    try:
        page = await context.new_page()
        await disable_bloating(page)

        await page.goto(url.url)
        extracted_metadata = await extract_metadata(page)
        tags = await extract_tags(page)
        article_text = await extract_text(page)

        # Load and extract comments
        await _click_see_all_responses(page)
        await _scroll_to_load_comments(page)
        comments = await _extract_comments(page)

        logging.info(f"Extracted metadata: {extracted_metadata}")
        logging.info(f"Tags: {tags}")
        logging.info(f"Article text preview: {article_text[:100]}...")
        logging.info(f"Extracted {len(comments)} comments: {comments[:2]}...")  # Log first 2 comments as sample

        await page.close()
        logging.info(f"Successfully scraped: {url.url}")
    except Exception as e:
        logging.error(f"Error scraping {url.url}: {str(e)}")

async def main():
    """Main function to scrape articles in parallel."""
    session = get_session()
    urls = session.query(URL).order_by(func.random()).limit(1).all()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            extra_http_headers=HEADERS
        )
        tasks = [scrape_article(url, context, session) for url in urls]
        await asyncio.gather(*tasks)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())