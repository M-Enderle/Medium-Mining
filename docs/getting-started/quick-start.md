# Quick Start Guide

This guide will help you quickly get up and running with Medium-Mining to scrape and analyze Medium articles.

## Prerequisites

Before starting, ensure you have:

- Installed Medium-Mining following the [Installation Guide](installation.md)
- Initialized the database as described in the installation instructions
- Installed Playwright browsers with `poetry run playwright install`

## Basic Workflow

The typical workflow with Medium-Mining consists of three main steps:

1. Scrape article URLs from Medium's sitemaps
2. Scrape content and metadata from individual articles
3. Analyze the collected data

## Step 1: Scrape Article URLs

The first step is to collect article URLs from Medium's sitemaps:

```bash
poetry run python -m scraper sitemap
```

This command will:

1. Retrieve Medium's master sitemap index
2. Process each individual sitemap
3. Extract article URLs and store them in the database
4. Skip sitemaps that have already been processed

### Options

You can customize the sitemap scraper with these options:

```bash
# Set a custom timeout between requests (in seconds)
poetry run python -m scraper sitemap --timeout 0.1

# Enable verbose logging to console
poetry run python -m scraper sitemap --verbose
```

### Monitoring Progress

The sitemap scraper logs its progress to `sitemap_scraper.log`. You can monitor this log in real-time:

```bash
tail -f sitemap_scraper.log
```

## Step 2: Scrape Article Content

Once you have collected article URLs, you can scrape the content and metadata:

```bash
poetry run python -m scraper article
```

This command will:

1. Retrieve random unprocessed URLs from the database
2. Open each URL in a browser (using Playwright)
3. Extract article content, metadata, and comments
4. Store the data in the database
5. Take screenshots for verification

### Options

You can customize the article scraper with these options:

```bash
# Specify the number of URLs to process
poetry run python -m scraper article --url-count 50

# Run browsers in headless mode (invisible)
poetry run python -m scraper article --headless true

# Use multiple worker threads for concurrent processing
poetry run python -m scraper article --workers 4
```

### Example: Full Configuration

Here's an example with all options set:

```bash
poetry run python -m scraper article --url-count 100 --headless true --workers 4
```

This will process 100 random URLs using 4 concurrent workers in headless mode.

### Monitoring Progress

The article scraper logs its progress to `article_scraper.log` and displays metrics on completion:

```bash
tail -f article_scraper.log
```

## Step 3: Analyze the Data

After collecting data, you can analyze it using the provided Jupyter notebooks:

1. Start Jupyter:

```bash
poetry run jupyter notebook
```

2. Open the analysis notebook:

```
notebooks/analyze_scraping_results.ipynb
```

3. Run the cells to explore the data

### Example Analysis

The notebook includes examples for:

- Counting the total number of collected URLs
- Visualizing article publication dates
- Analyzing change frequency patterns
- Exploring sitemap structure
- Correlating article metrics

### Custom Analysis

You can create your own analysis by:

1. Copying the example notebook
2. Modifying the queries to extract the data you're interested in
3. Creating custom visualizations
4. Adding your own analytical techniques

## Complete Workflow Example

Here's a complete example workflow:

```bash
# 1. Initialize the database
poetry run python -m database.database

# 2. Scrape sitemaps with verbose output
poetry run python -m scraper sitemap --verbose

# 3. Scrape 200 articles with 4 workers
poetry run python -m scraper article --url-count 200 --workers 4 --headless true

# 4. Run Jupyter for analysis
poetry run jupyter notebook notebooks/analyze_scraping_results.ipynb
```

## Tips for Effective Use

### Performance Optimization

- **Headless Mode**: Use `--headless true` for faster processing
- **Worker Threads**: Use `--workers` to match your CPU cores (typically 4-8)
- **Batch Size**: Process manageable batches (50-100) at a time
- **Database Indexing**: The database schema includes indexes for efficient querying

### Resource Management

- **Disk Space**: Monitor database size, which grows with the number of articles
- **Memory Usage**: Each browser instance requires memory; adjust worker count accordingly
- **CPU Usage**: Multiple workers can lead to high CPU utilization

### Ethical Considerations

- **Rate Limiting**: Use reasonable timeouts (0.05-0.1 seconds) between sitemap requests
- **Concurrency**: Avoid excessive concurrent requests to Medium's servers
- **Purpose**: Use the collected data for research and educational purposes only

## Next Steps

Now that you're familiar with the basic workflow, you can:

- Learn more about the [Sitemap Scraper](../modules/scraper/sitemap-scraper.md)
- Explore the [Article Scraper](../modules/scraper/article-scraper.md) in depth
- Understand the [Database Schema](../architecture/database-schema.md)
- Try advanced [Data Analysis](../data-analysis/overview.md) techniques
- Configure Medium-Mining for your specific needs

## Troubleshooting

If you encounter issues, check:

- **Logs**: Review `sitemap_scraper.log` and `article_scraper.log`
- **Screenshots**: Examine screenshots in the `screenshots/` directory
- **Database**: Verify data in the database using the analysis notebooks
- **FAQ**: See the [FAQ](../faq/faq.md) and [Common Issues](../faq/common-issues.md) sections