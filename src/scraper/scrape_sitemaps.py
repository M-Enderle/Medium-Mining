# scraper.py
import logging
import random
import time
import xml.etree.ElementTree as ET
import asyncio
import aiohttp

from database.database import URL, Sitemap, AsyncSessionLocal

SITEMAP_URL = "https://medium.com/sitemap/sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MediumScraper/1.0)"}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="sitemap_scraper.log",
)


def get_random_timeout(avg_timeout: int) -> float:
    """Generate a random timeout with normal distribution around the average."""
    return max(0.1, random.gauss(avg_timeout, avg_timeout / 2))


async def retrieve_sitemaps(timeout_average: int) -> bool:
    """
    Retrieve and process sitemaps with error handling and logging.
    Returns True if successful, False otherwise.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Check if master sitemap was already processed
            result = await session.execute(
                Sitemap.__table__.select().where(Sitemap.sitemap_url == SITEMAP_URL)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                logging.info(f"Master sitemap {SITEMAP_URL} already processed")
                return True

            # Retrieve the master sitemap
            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(SITEMAP_URL, headers=HEADERS, timeout=10) as response:
                    if response.status != 200:
                        logging.error(
                            f"Failed to retrieve master sitemap: {response.status}"
                        )
                        return False
                    
                    content = await response.text()

            root = ET.fromstring(content)
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            sitemap_urls = [
                elem.find("ns:loc", ns).text for elem in root.findall("ns:sitemap", ns)
            ]

            logging.info(f"Found {len(sitemap_urls)} sitemaps")

            async with aiohttp.ClientSession() as http_session:
                for sitemap_url in sitemap_urls:
                    # Check if this sitemap was already processed
                    result = await session.execute(
                        Sitemap.__table__.select().where(Sitemap.sitemap_url == sitemap_url)
                    )
                    if result.scalar_one_or_none():
                        logging.info(f"Sitemap {sitemap_url} already processed, skipping")
                        continue

                    await asyncio.sleep(get_random_timeout(timeout_average))

                    try:
                        async with http_session.get(sitemap_url, headers=HEADERS, timeout=10) as response:
                            if response.status != 200:
                                logging.warning(
                                    f"Failed to retrieve sitemap {sitemap_url}: {response.status}"
                                )
                                continue
                            
                            content = await response.text()

                        root = ET.fromstring(content)
                        urls = root.findall("ns:url", ns)

                        sitemap = Sitemap(sitemap_url=sitemap_url, articles_count=len(urls))
                        session.add(sitemap)
                        await session.flush()
                        logging.info(
                            f"Processing sitemap: {sitemap_url} with {len(urls)} URLs"
                        )

                        for url_elem in urls:
                            url = url_elem.find("ns:loc", ns).text
                            lastmod = (
                                url_elem.find("ns:lastmod", ns).text
                                if url_elem.find("ns:lastmod", ns) is not None
                                else None
                            )
                            changefreq = (
                                url_elem.find("ns:changefreq", ns).text
                                if url_elem.find("ns:changefreq", ns) is not None
                                else None
                            )
                            priority = (
                                url_elem.find("ns:priority", ns).text
                                if url_elem.find("ns:priority", ns) is not None
                                else None
                            )

                            url_entry = URL(
                                sitemap_id=sitemap.id,
                                url=url,
                                last_modified=lastmod,
                                change_freq=changefreq,
                                priority=priority,
                            )
                            session.add(url_entry)

                        await session.commit()
                        logging.info(f"Successfully processed sitemap: {sitemap_url}")

                    except Exception as e:
                        logging.error(f"Error processing sitemap {sitemap_url}: {str(e)}")
                        await session.rollback()
                        continue

            return True

    except Exception as e:
        logging.error(f"Fatal error in retrieve_sitemaps: {str(e)}")
        return False


async def main():
    """Main entry point for the sitemap scraper."""
    timeout_average = 2  # Average timeout in seconds
    success = await retrieve_sitemaps(timeout_average)
    if success:
        logging.info("Sitemap processing completed successfully")
    else:
        logging.error("Sitemap processing failed")


if __name__ == "__main__":
    asyncio.run(main())
