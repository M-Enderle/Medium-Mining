import argparse
import asyncio
import logging
import sys

from scraper.scrape_articles import main as scrape_articles_main
from scraper.scrape_sitemaps import retrieve_sitemaps


async def run_sitemap_scraper(args):
    """Run the sitemap scraper with the provided arguments"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename="sitemap_scraper.log",
    )

    # Add console handler if verbose is enabled
    if args.verbose:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logging.getLogger().addHandler(console_handler)

    # Run the scraper
    logging.info(
        f"Starting sitemap scraper with timeout average: {args.timeout} seconds"
    )
    success = await retrieve_sitemaps(args.timeout)

    if success:
        logging.info("Sitemap scraping completed successfully")
        return 0
    else:
        logging.error("Sitemap scraping failed")
        return 1


def run_article_scraper(args):
    """Run the article scraper with the provided arguments"""
    # The article scraper already has its own logging configuration
    if args.url_count:
        # Modify the fetch_random_urls function's behavior
        import scraper.medium_helpers

        scraper.medium_helpers.URLS_TO_FETCH = args.url_count

    # Handle headless mode
    if args.headless is not None:
        import scraper.scrape_articles

        scraper.scrape_articles.HEADLESS = args.headless

    # Handle worker count
    if args.workers:
        import scraper.scrape_articles

        scraper.scrape_articles.MAX_CONCURRENT = args.workers

    try:
        scrape_articles_main()
        return 0
    except Exception as e:
        logging.error(f"Article scraper failed: {e}")
        return 1


async def async_main():
    """Main async function to parse arguments and dispatch to the appropriate scraper"""
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Medium Scraper Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Sitemap scraper subparser
    sitemap_parser = subparsers.add_parser("sitemap", help="Scrape Medium sitemaps")
    sitemap_parser.add_argument(
        "--timeout",
        type=float,
        default=0.05,
        help="Average timeout between requests in seconds (default: 0.05)",
    )
    sitemap_parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose output to console"
    )

    # Article scraper subparser
    article_parser = subparsers.add_parser("article", help="Scrape Medium articles")
    article_parser.add_argument(
        "--url-count", type=int, help="Number of URLs to process"
    )
    article_parser.add_argument(
        "--headless",
        type=bool,
        help="Run browser in headless mode (default: False)",
        default=None,
        action="store_true"
    )
    article_parser.add_argument(
        "--workers",
        type=int,
        help="Number of concurrent workers (default: 1)",
    )

    args = parser.parse_args()

    if args.command == "sitemap":
        return await run_sitemap_scraper(args)
    elif args.command == "article":
        return run_article_scraper(args)
    else:
        parser.print_help()
        return 0


def main():
    """Entry point for the script - runs the async main function"""
    sys.exit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
