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

## Usage

### Scraping Sitemaps

To scrape Medium sitemaps and collect article URLs, run the following command:

```bash
poetry run python src/scraper/scrape_sitemaps.py
```

### Scraping Articles

To scrape detailed content and metadata from Medium articles, run the following command:

```bash
poetry run python src/scraper/scrape_articles.py --url_count 5000 --workers 5 --headless
```

- `--url_count`: Number of URLs to process (default: 100)
- `--workers`: Number of worker threads (default: 5)
- `--headless`: Run browser in headless mode
- `--with_login`: Login to Medium. Requires a `login_state.json`.

### Logging Metrics with wandb

The `src/scraper/scrape_articles.py` script uses `wandb` for logging metrics. To enable logging, ensure you have a `wandb` account and initialize it with your project details.

```python
import wandb

wandb.init(project="medium-scraper", entity="your_entity")
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

## Scraper Directory

The `src/scraper` directory contains scripts for scraping Medium articles and sitemaps:

- `scrape_articles.py`: Extracts detailed content and metadata from Medium articles.
- `scrape_sitemaps.py`: Crawls Medium sitemaps to collect article URLs.

## Use of wandb

The `src/scraper/scrape_articles.py` script uses `wandb` for logging metrics.

## Database Directory

The `src/database` directory contains scripts for managing the database:

- `database.py`: Defines the database schema and provides functions for database operations.
- `recreate_db.py`: Recreates the database from an existing database file.
- `transfer_data.py`: Transfers data from an SQLite database to a DuckDB database.

## pyproject.toml

The `pyproject.toml` file includes the project dependencies and configuration for Poetry.
