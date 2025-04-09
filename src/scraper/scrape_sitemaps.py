# scraper.py
import logging
import random
import time
import xml.etree.ElementTree as ET

import requests

from database.database import URL, Sitemap, get_session

SITEMAP_URL = "https://medium.com/sitemap/sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MediumScraper/1.0)"}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("sitemap_scraper.log"), logging.StreamHandler()],
)


def get_random_timeout(avg_timeout: int) -> float:
    """Generate a random timeout with normal distribution around the average."""
    return max(0.1, random.gauss(avg_timeout, avg_timeout / 2))


def process_url_element(url_elem, ns, sitemap_id):
    """Extract URL information from an XML element and create a URL object."""
    url = url_elem.find("ns:loc", ns).text

    lastmod = url_elem.find("ns:lastmod", ns)
    lastmod = lastmod.text if lastmod is not None else None

    changefreq = url_elem.find("ns:changefreq", ns)
    changefreq = changefreq.text if changefreq is not None else None

    update_freq_mapping = {
        "always": 0,
        "hourly": 1,
        "daily": 2,
        "monthly": 3,
    }
    changefreq = update_freq_mapping.get(changefreq, None)

    priority = url_elem.find("ns:priority", ns)
    priority = float(priority.text) if priority is not None else None

    return URL(
        sitemap_id=sitemap_id,
        url=url,
        last_modified=lastmod,
        change_freq=changefreq,
        priority=priority,
    )


def process_sitemap_content(sitemap_url, content, session, ns):
    """Process the content of a sitemap and store URLs in the database."""
    try:
        root = ET.fromstring(content)
        urls = root.findall("ns:url", ns)

        # Create sitemap entry
        sitemap = Sitemap(sitemap_url=sitemap_url, articles_count=len(urls))
        session.add(sitemap)
        session.flush()
        logging.info(f"Processing sitemap: {sitemap_url} with {len(urls)} URLs")

        # Process URLs in batches for better performance
        batch_size = 100
        for i in range(0, len(urls), batch_size):
            batch = urls[i : i + batch_size]
            url_entries = [
                process_url_element(url_elem, ns, sitemap.id) for url_elem in batch
            ]
            session.bulk_save_objects(url_entries)

        session.commit()
        logging.info(f"Successfully processed sitemap: {sitemap_url}")
        return True
    except Exception as e:
        logging.error(f"Error processing sitemap content {sitemap_url}: {str(e)}")
        session.rollback()
        return False


def retrieve_sitemaps(timeout_average: int) -> bool:
    """
    Retrieve and process sitemaps with error handling and logging.
    Returns True if successful, False otherwise.
    """
    try:
        session = get_session()
        # Check if master sitemap was already processed
        existing = (
            session.query(Sitemap).filter(Sitemap.sitemap_url == SITEMAP_URL).first()
        )

        if existing:
            logging.info(f"Master sitemap {SITEMAP_URL} already processed")
            return True

        # Retrieve the master sitemap
        response = requests.get(SITEMAP_URL, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            logging.error(f"Failed to retrieve master sitemap: {response.status_code}")
            return False

        content = response.text
        root = ET.fromstring(content)
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_urls = [
            elem.find("ns:loc", ns).text for elem in root.findall("ns:sitemap", ns)
        ]

        logging.info(f"Found {len(sitemap_urls)} sitemaps")

        for sitemap_url in sitemap_urls:
            # Check if this sitemap was already processed
            existing_sitemap = (
                session.query(Sitemap)
                .filter(Sitemap.sitemap_url == sitemap_url)
                .first()
            )

            if existing_sitemap:
                logging.info(f"Sitemap {sitemap_url} already processed, skipping")
                continue

            time.sleep(get_random_timeout(timeout_average))

            try:
                response = requests.get(sitemap_url, headers=HEADERS, timeout=10)
                if response.status_code != 200:
                    logging.warning(
                        f"Failed to retrieve sitemap {sitemap_url}: {response.status_code}"
                    )
                    continue

                process_sitemap_content(sitemap_url, response.text, session, ns)

            except Exception as e:
                logging.error(f"Error retrieving sitemap {sitemap_url}: {str(e)}")
                continue

        return True

    except Exception as e:
        logging.error(f"Fatal error in retrieve_sitemaps: {str(e)}")
        return False


def main():
    """Main entry point for the sitemap scraper."""
    timeout_average = 2  # Average timeout in seconds
    success = retrieve_sitemaps(timeout_average)
    if success:
        logging.info("Sitemap processing completed successfully")
    else:
        logging.error("Sitemap processing failed")


if __name__ == "__main__":
    main()
