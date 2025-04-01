# Getting Started

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/username/Medium-Mining.git
   cd Medium-Mining
   ```

2. Install dependencies using Poetry:
   ```bash
   poetry install
   ```

3. Initialize the database:
   ```bash
   poetry run python -m database.database
   ```

## Usage

### Scraping Medium Sitemaps

To scrape Medium sitemaps for article URLs:

```bash
poetry run python -m scraper sitemap [--timeout 0.05] [--verbose]
```

Options:
- `--timeout`: Time to wait between requests (default: 0.05 seconds)
- `--verbose`: Enable verbose logging

### Scraping Medium Articles

To scrape article content and metadata:

```bash
poetry run python -m scraper article [--url-count 50] [--headless true] [--workers 1]
```

Options:
- `--url-count`: Number of article URLs to scrape (default: 50)
- `--headless`: Run browser in headless mode (default: true)
- `--workers`: Number of worker processes (default: 1)

## Development

For code formatting:

```bash
poetry run black src/ && poetry run isort src/
```