# Scraper Module

The scraper module contains functionality for scraping Medium sitemaps and articles.

## Components

### Sitemap Scraper

The sitemap scraper extracts article URLs from Medium's sitemaps.

```bash
poetry run python -m scraper sitemap [--timeout 0.05] [--verbose]
```

### Article Scraper

The article scraper extracts content and metadata from Medium articles.

```bash
poetry run python -m scraper article [--url-count 50] [--headless true] [--workers 1]
```

## Module Structure

- `__main__.py` - Entry point for the scraper CLI
- `scrape_sitemaps.py` - Functionality for scraping sitemaps
- `scrape_articles.py` - Functionality for scraping article content
- `medium_helpers.py` - Helper functions for interacting with Medium