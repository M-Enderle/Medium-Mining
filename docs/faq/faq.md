# Frequently Asked Questions

This page answers common questions about the Medium-Mining project.

## General Questions

### What is Medium-Mining?

Medium-Mining is a Python-based project designed to extract and analyze content from Medium.com. It includes tools for scraping article URLs from sitemaps, extracting detailed content and metadata from articles, and analyzing the collected data.

### What can I do with Medium-Mining?

Medium-Mining enables you to:

- Collect article URLs from Medium's sitemaps
- Extract article content, metadata, and comments
- Store the data in a structured database
- Analyze the data using provided notebooks
- Export the data for use with external tools

### Is using Medium-Mining legal?

Medium-Mining is provided for research and educational purposes only. Always check Medium's Terms of Service before using this tool. Some considerations:

- Always include reasonable delays between requests
- Respect Medium's robots.txt file
- Do not use the data for commercial purposes without proper authorization
- Do not republish Medium content without permission

### What are the system requirements?

- Python 3.13 or newer
- 2GB+ of RAM
- Sufficient disk space for the database (size depends on the amount of data collected)
- Internet connection
- Operating system: Windows, macOS, or Linux

## Installation Questions

### Why does Poetry installation fail?

If you encounter issues installing dependencies with Poetry, try:

1. Check your Python version: `python --version` (ensure it's 3.13+)
2. Update Poetry: `poetry self update`
3. Clear Poetry cache: `poetry cache clear pypi --all`
4. Try with verbose output: `poetry install -v`

### Why does Playwright installation fail?

Playwright installation issues are usually related to missing system dependencies. Try:

```bash
# Install Playwright manually
pip install playwright
playwright install --with-deps chromium
```

For Linux users, you might need additional packages. See the [installation guide](../getting-started/installation.md) for details.

### Can I use Medium-Mining without Poetry?

Yes, you can install the dependencies manually using pip:

```bash
pip install -r requirements.txt
pip install playwright
playwright install
```

Note that this approach might not guarantee the exact versions specified in `pyproject.toml`.

## Usage Questions

### How many URLs can I scrape?

The number of URLs you can scrape depends on:

- Your internet connection
- System resources
- Time constraints
- Ethical considerations regarding server load

As a guideline, start with a small number (e.g., 50-100) and gradually increase as needed.

### How do I scrape member-only articles?

Medium-Mining can detect member-only articles but cannot access their full content without a Medium membership. The scraper will still extract available metadata and indicate that the article is member-only.

### How do I increase scraping speed?

To improve scraping speed:

- Increase the number of worker threads with `--workers`
- Use headless mode with `--headless true`
- Run on a machine with a faster internet connection
- Optimize your database configuration

However, always maintain ethical scraping practices with reasonable delays.

### Can I pause and resume scraping?

The scraper doesn't have built-in pause/resume functionality. However, since processed URLs are marked in the database, you can simply stop and restart the scraper, and it will continue with unprocessed URLs.

## Database Questions

### How do I view the collected data?

You can view the collected data in several ways:

1. Use the provided Jupyter notebooks in the `notebooks/` directory
2. Connect to the DuckDB database with a SQL client
3. Use SQLAlchemy in your own Python scripts
4. Export the data to CSV or JSON formats

### How large can the database become?

The database size depends on the number of articles you scrape and their content. As a rough estimate:

- Each sitemap entry: ~100 bytes
- Each URL entry: ~500 bytes
- Each article (with comments): ~10-100 KB

A collection of 10,000 articles might require 100MB-1GB of storage.

### Can I use a different database backend?

Yes, Medium-Mining uses SQLAlchemy, which supports multiple database backends. To use a different backend:

1. Modify the `DATABASE_URL` in `src/database/database.py`
2. Install the appropriate database driver
3. Update any database-specific code if needed

For example, to use PostgreSQL:

```python
DATABASE_URL = "postgresql://username:password@localhost/medium_articles"
```

### How do I back up the database?

For DuckDB, you can simply copy the database file:

```bash
cp medium_articles.duckdb medium_articles_backup.duckdb
```

For other database backends, use the appropriate backup procedure for that database system.

## Scraping Questions

### Why do I get "Timeout Error" when scraping articles?

Timeout errors can occur for several reasons:

- Slow internet connection
- Medium's server is slow to respond
- The page has complex content that takes time to load
- Your system is under high load

Try increasing the timeout parameter or reducing the number of concurrent workers.

### Why does the scraper show "Failed to click responses button"?

This warning appears when the scraper cannot find or click the "See all responses" button on a Medium article. This can happen if:

- The article has no comments
- Medium has changed their UI
- The button is not yet visible (needs scrolling)

This warning is not critical and can be ignored if you're not primarily interested in comments.

### How do I handle CAPTCHA or bot detection?

If Medium starts showing CAPTCHAs or blocking the scraper:

1. Reduce the scraping frequency (increase timeouts)
2. Run in non-headless mode to manually solve CAPTCHAs
3. Try changing the browser configuration
4. Use a different IP address or proxy

### Can I scrape only specific topics or authors?

The current implementation scrapes URLs from sitemaps, which doesn't allow filtering by topic or author. However, you could:

1. Scrape a broader set of articles
2. Filter the results in your analysis phase
3. Or modify the code to first extract URLs from specific topic or author pages

## Analysis Questions

### How do I perform custom analysis?

To create your own analysis:

1. Copy one of the example notebooks in the `notebooks/` directory
2. Modify the queries and visualizations as needed
3. Use SQLAlchemy to create custom queries
4. Leverage pandas, matplotlib, and other data analysis libraries

### Can I use NLP tools with the collected data?

Yes, the article text is stored in the database and can be used with NLP tools:

1. Extract the article text from the database
2. Use libraries like NLTK, spaCy, or Transformers for analysis
3. Implement techniques like:
   - Topic modeling
   - Sentiment analysis
   - Named entity recognition
   - Text summarization

### How do I visualize the results?

The notebooks include examples using matplotlib and seaborn. You can also:

- Use other Python visualization libraries like Plotly or Bokeh
- Export the data to tools like Tableau or Power BI
- Create custom visualizations based on your specific needs

### Can I export the data for use with other tools?

Yes, you can export the data to various formats:

- CSV for spreadsheet applications
- JSON for web applications
- SQL dumps for other database systems
- Custom formats for specific tools

See the [Export Data](../data-analysis/export-data.md) guide for examples.

## Troubleshooting

For solutions to common problems, see the [Common Issues](common-issues.md) and [Debugging](debugging.md) guides.

If your question isn't answered here, consider:

- Checking the [GitHub Issues](https://github.com/M-Enderle/Medium-Mining/issues) for similar problems
- Creating a new issue with a detailed description of your problem
- Contributing to this FAQ if you find a solution to a common problem