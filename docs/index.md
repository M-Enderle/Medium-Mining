# Medium-Mining Project

<figure markdown>
  ![Medium-Mining Logo](assets/logo.png){ width="300" }
  <figcaption>A comprehensive tool for scraping and analyzing Medium articles</figcaption>
</figure>

## Overview

Medium-Mining is a sophisticated Python-based toolset designed for extracting, storing, and analyzing content from Medium.com. This project offers a powerful way to collect data from Medium's vast repository of articles, comments, and associated metadata for research, analysis, or archival purposes.

### Key Features

- **Efficient Sitemap Crawling**: Asynchronously retrieve article URLs from Medium's sitemaps
- **Comprehensive Article Scraping**: Extract detailed content including text, author information, claps, comments, and more
- **Robust Database Storage**: Store all data in a structured DuckDB database for efficient querying
- **Configurable Execution**: Control execution parameters like concurrency, rate limiting, and browser visibility
- **Detailed Logging**: Track progress and diagnose issues with comprehensive logging
- **Support for All Article Types**: Handle both member-only and public articles
- **Performance Metrics**: Monitor scraping performance with built-in metrics

## Project Components

The project consists of two main components:

1. **Sitemap Scraper**: 
   - Crawls Medium's XML sitemaps
   - Collects and stores article URLs
   - Efficiently handles large sitemaps with batch processing

2. **Article Scraper**:
   - Extracts complete article content and metadata
   - Captures comments and user interactions
   - Uses browser automation with Playwright for rendering JavaScript content
   - Manages browser sessions for optimal performance

## Getting Started

To get started with Medium-Mining, check out the [Installation](getting-started/installation.md) guide, then proceed to the [Quick Start](getting-started/quick-start.md) section for basic usage instructions.

## Use Cases

Medium-Mining is designed for:

- **Content Analysis**: Study writing styles, trends, and popular topics
- **Sentiment Analysis**: Analyze article content and comment sentiment
- **Research**: Collect data for academic or market research
- **Content Aggregation**: Gather articles for creating curated collections
- **Temporal Analysis**: Track how content changes over time

## Sample Results

The following visualization shows the distribution of article publication dates from a sample scrape:

<figure markdown>
  ![Publication Date Distribution](assets/sample_visualization.png){ width="600" }
  <figcaption>Distribution of Medium articles by publication date</figcaption>
</figure>

## Important Notice

This tool is provided for research and educational purposes only. Always adhere to Medium's [Terms of Service](https://policy.medium.com/medium-terms-of-service-9db0094a1e0f) and [robots.txt](https://medium.com/robots.txt) when using this software. Be respectful of Medium's servers by using reasonable rate limiting.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/M-Enderle/Medium-Mining/blob/main/LICENSE) file for details.