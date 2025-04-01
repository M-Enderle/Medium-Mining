# Common Issues

This page covers common issues you might encounter when using Medium-Mining and provides solutions.

## Installation Issues

### Poetry Dependency Resolution Failures

**Issue**: Poetry fails to resolve dependencies with an error like `Could not find a matching version of package X`.

**Solution**:
1. Update Poetry: `poetry self update`
2. Clear Poetry's cache: `poetry cache clear --all pypi`
3. Try using more flexible version constraints in `pyproject.toml`
4. Ensure Python version matches requirements (3.13+)

### Playwright Installation Failures

**Issue**: Playwright browser installation fails with permission errors or missing dependencies.

**Solution**:
```bash
# Install manually with elevated permissions
sudo pip install playwright
sudo playwright install --with-deps chromium
```

For specific operating systems, see the [Playwright installation docs](https://playwright.dev/python/docs/browsers).

### DuckDB Installation Issues

**Issue**: DuckDB fails to install or import with cryptic errors.

**Solution**:
1. Install required system dependencies:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install -y python3-dev
   
   # macOS
   brew install python
   ```
2. Try installing a specific version: `pip install duckdb==1.1.0`
3. For M1/M2 Macs, ensure you're using Python built for arm64

## Scraping Issues

### Sitemap Scraper Failures

**Issue**: Sitemap scraper fails with connection errors.

**Solution**:
1. Check your internet connection
2. Increase timeout values: `--timeout 0.2`
3. Verify Medium's sitemap structure hasn't changed
4. Check the `sitemap_scraper.log` for detailed error messages

### Article Scraper Browser Errors

**Issue**: Article scraper fails with browser-related errors like:
- `Error: Browser closed unexpectedly`
- `Error: Timeout 30000ms exceeded`
- `Error: Target closed`

**Solution**:
1. Ensure Playwright is properly installed: `playwright install --with-deps chromium`
2. Reduce the number of concurrent workers: `--workers 2`
3. Run in non-headless mode for debugging: `--headless false`
4. Check system resources (memory, CPU)
5. Examine the screenshots in the `screenshots/` directory

### Medium Detection and Blocking

**Issue**: Medium detects the scraper as a bot and shows captchas or blocks access.

**Solution**:
1. Increase delays between requests
2. Reduce concurrency
3. Modify browser configuration in `scrape_articles.py`:
   ```python
   context = browser.new_context(
       viewport={"width": 1280, "height": 800},  # More standard desktop size
       user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
       locale="en-US",
   )
   ```
4. Use rotating IP addresses or proxies
5. Run in non-headless mode and manually solve captchas

### Article Data Extraction Issues

**Issue**: The scraper fails to extract certain article elements (comments, text, etc.).

**Solution**:
1. Medium may have changed their UI structure
2. Update the selectors in `medium_helpers.py`
3. For comments issues, check if comments are loaded dynamically
4. Try running in non-headless mode to visually inspect the page
5. Increase wait times for page elements to load

## Database Issues

### Database Connection Errors

**Issue**: Unable to connect to the database with errors like:
- `OperationalError: unable to open database file`
- `Permission denied`

**Solution**:
1. Check file permissions on the database file
2. Ensure the directory exists and is writable
3. Try connecting with a different tool to isolate the issue
4. Use absolute paths in `DATABASE_URL`

### Database Schema Errors

**Issue**: Errors like `no such table` or `no such column` when querying.

**Solution**:
1. Ensure the database was properly initialized: `python -m database.database`
2. Check if you're using the latest version of the code
3. For migration issues, consider:
   ```python
   # Recreate tables (caution: this will delete existing data)
   Base.metadata.drop_all(engine)
   Base.metadata.create_all(engine)
   ```

### Data Integrity Issues

**Issue**: Data inconsistencies or missing relationships.

**Solution**:
1. Check that transactions are properly committed
2. Use a database browser to examine the data
3. Add validation logic to data insertion functions
4. Use SQLAlchemy's relationship constraints
5. Implement proper error handling with rollbacks

## Analysis Issues

### Jupyter Notebook Kernel Errors

**Issue**: Jupyter notebook fails to start or connect to the kernel.

**Solution**:
1. Install ipykernel: `pip install ipykernel`
2. Register the kernel: `python -m ipykernel install --user`
3. Restart Jupyter: `jupyter notebook`
4. Try using JupyterLab instead: `jupyter lab`

### Data Visualization Errors

**Issue**: Matplotlib or Seaborn plots fail to display.

**Solution**:
1. Ensure the appropriate backend is set: `%matplotlib inline`
2. Check for missing dependencies: `pip install matplotlib seaborn`
3. Restart the kernel
4. Try alternative plotting libraries: `import plotly.express as px`

### Performance Issues with Large Datasets

**Issue**: Analysis is slow or crashes with large datasets.

**Solution**:
1. Use sampling: `df.sample(n=1000)` or `query.limit(1000)`
2. Optimize SQL queries with proper indexing
3. Use DuckDB's analytical capabilities
4. Process data in chunks
5. Consider dedicated data analysis tools for very large datasets

## System Resource Issues

### High Memory Usage

**Issue**: The scraper consumes excessive memory, especially with multiple workers.

**Solution**:
1. Reduce the number of concurrent workers: `--workers 2`
2. Process fewer URLs at a time: `--url-count 20`
3. Close browser contexts promptly after use
4. Monitor memory usage with tools like `htop` or Activity Monitor
5. Implement garbage collection where appropriate

### CPU Utilization

**Issue**: The scraper uses 100% CPU, slowing down the system.

**Solution**:
1. Reduce the number of concurrent workers
2. Introduce delays between processing: `time.sleep(1)`
3. Run with lower process priority:
   ```bash
   # Linux/macOS
   nice -n 10 poetry run python -m scraper article
   
   # Windows PowerShell
   Start-Process -Priority BelowNormal -FilePath python -ArgumentList "-m scraper article"
   ```

### Disk Space Issues

**Issue**: The database file grows very large.

**Solution**:
1. Process data in smaller batches
2. Implement data retention policies
3. Archive or export old data
4. Use database compression features
5. Consider database vacuum/optimization:
   ```python
   engine.execute("VACUUM")
   ```

## Command-Line Interface Issues

### Command Not Found

**Issue**: Getting `command not found` or similar errors when running commands.

**Solution**:
1. Ensure Poetry environment is activated: `poetry shell`
2. Use the full command with Poetry: `poetry run python -m scraper article`
3. Check that the package is properly installed: `poetry install`
4. Verify the correct Python version is being used

### Command-Line Argument Errors

**Issue**: Arguments not being recognized or incorrect behavior.

**Solution**:
1. Double-check argument syntax
2. Use `--help` to see available options: `python -m scraper article --help`
3. For boolean flags, use explicit values: `--headless true`
4. Check for version mismatches between code and documentation

## Debugging Techniques

### Enabling Verbose Logging

To get more information about what's happening:

```bash
# For sitemap scraper
poetry run python -m scraper sitemap --verbose

# For general Python debugging
PYTHONVERBOSE=1 poetry run python -m scraper article
```

### Using Screenshots

The article scraper automatically takes screenshots. Examine them to understand what the browser is seeing:

```bash
# Open the screenshots directory
open screenshots/
```

### Database Inspection

Directly examine the database with DuckDB's CLI:

```bash
duckdb medium_articles.duckdb

# Then run SQL queries
SELECT COUNT(*) FROM urls;
SELECT COUNT(*) FROM medium_articles;
```

### Network Debugging

To debug network issues, capture network traffic:

```bash
# Linux
sudo tcpdump -n -s 0 host medium.com -w medium_traffic.pcap

# macOS
sudo tcpdump -n -s 0 host medium.com -w medium_traffic.pcap

# Windows
# Use Wireshark
```

### Process Monitoring

Monitor the process during execution:

```bash
# Linux/macOS
htop -p $(pgrep -f "python.*scraper")

# Windows
# Use Task Manager
```

## Advanced Troubleshooting

For issues that persist after trying the solutions above:

1. **Debug Mode**: Run Python with debugging enabled:
   ```bash
   python -m pdb -m scraper article
   ```

2. **Code Inspection**: Temporarily modify the code to add debug prints:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **Interactive Debugging**: Use IPython for interactive debugging:
   ```python
   import IPython; IPython.embed()  # Add this line where you want to inspect
   ```

4. **Simplified Reproduction**: Create a minimal example that reproduces the issue

5. **GitHub Issues**: Search for or create an issue on the [GitHub repository](https://github.com/M-Enderle/Medium-Mining/issues)