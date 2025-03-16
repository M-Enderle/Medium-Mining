# __main__.py
import argparse
import logging
from scraper.scrape_sitemaps import retrieve_sitemaps

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='sitemap_scraper.log'
    )

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Medium Sitemap Scraper")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.05,
        help="Average timeout between requests in seconds (default: 5)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to console"
    )
    
    args = parser.parse_args()

    # Add console handler if verbose is enabled
    if args.verbose:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        logging.getLogger().addHandler(console_handler)

    # Run the scraper
    logging.info(f"Starting sitemap scraper with timeout average: {args.timeout} seconds")
    success = retrieve_sitemaps(args.timeout)
    
    if success:
        logging.info("Sitemap scraping completed successfully")
    else:
        logging.error("Sitemap scraping failed")
        exit(1)

if __name__ == "__main__":
    main()