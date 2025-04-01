# Database Module

The database module handles the storage and retrieval of scraped Medium data.

## Initialization

Initialize the database with:

```bash
poetry run python -m database.database
```

## Module Structure

- `database.py` - Contains database models, connection logic, and utility functions

## Schema

The database stores information about:

- Article URLs from sitemaps
- Article content and metadata
- Publishing information
- Tags and categories

## Usage Example

```python
from database.database import session, Article

# Query all articles
articles = session.query(Article).all()

# Get articles with a specific tag
tagged_articles = session.query(Article).filter(Article.tags.contains(['programming'])).all()
```