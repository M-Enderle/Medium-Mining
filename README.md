# Medium-Mining

A comprehensive tool for scraping and analyzing Medium articles and their metadata.

## Project Overview

Medium-Mining is a Python-based tool designed to extract and analyze content from Medium.com. The project consists of two main components:

1. **Sitemap Scraper**: Crawls Medium sitemaps to collect article URLs.
2. **Article Scraper**: Extracts detailed content and metadata from Medium articles, including:
   - Article text
   - Author information
   - Publication date
   - Comments
   - Claps (likes)
   - Tags

All data is stored in a DuckDB database for efficient analysis and querying.

## Features

- Asynchronous sitemap crawling for efficient URL collection
- Browser-based article scraping with Playwright
- Support for both member-only and public articles
- Comment extraction and analysis
- Configurable concurrency and rate limiting
- Persistent database storage

## Installation

```bash
# Install with Poetry
poetry install

# Initialize the database
poetry run python -m database.database

# initialize playwright
poetry run playwright install
```

## Database Schema

The project uses SQLAlchemy with the following main models:

- **Sitemap**: Stores sitemap URLs and article counts
- **URL**: Stores article URLs with metadata and crawl status
- **MediumArticle**: Stores article content and metadata
- **Comment**: Stores article comments with metadata

## Requirements

- Python 3.13+
- Dependencies managed through Poetry

## License

MIT