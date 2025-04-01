# Data Analysis Overview

The Medium-Mining project includes tools and examples for analyzing the data collected by the scrapers. This section provides an overview of the data analysis capabilities and demonstrates how to extract insights from the collected Medium articles.

## Analysis Components

The data analysis components of the Medium-Mining project are primarily contained within Jupyter notebooks:

```
notebooks/
├── analyze_scraping_results.ipynb  # Primary analysis notebook
└── custom_analyses/                # Directory for user-created analysis notebooks
```

## Prerequisites

Before conducting analysis, ensure you have:

1. Populated your database with Medium article data using the sitemap and article scrapers
2. Installed the required Python packages for data analysis:
   - pandas
   - matplotlib
   - seaborn
   - scipy
   - numpy
   - jupyter

These packages are already included in the Poetry dependencies.

## Key Analysis Capabilities

The Medium-Mining data analysis toolset enables several types of analyses:

### Article Metadata Analysis

- Publication date trends
- Author productivity
- Clap (like) distribution
- Tag frequency and correlation
- Content type distribution (member-only vs. public articles)

### Content Analysis

- Article length analysis
- Word frequency and topic modeling
- Keyword extraction and analysis
- Sentiment analysis

### Comment Analysis

- Comment volume per article
- Clap distribution on comments
- User engagement patterns
- Comment sentiment analysis

### Temporal Analysis

- Publishing trends over time
- Content evolution
- Engagement patterns

## Sample Analysis

Here's a sample analysis of article publication dates:

```python
# Connect to the database
from database.database import URL, Sitemap, get_session
import seaborn as sns
from sqlalchemy.sql import func
import matplotlib.pyplot as plt
import datetime
import pandas as pd

session = get_session()

# Get total number of URLs
total_urls = session.query(URL).count()
print(f'Total URLs in the database: {total_urls}')

# Plot article creation time
def plot_creation_time():
    urls = session.query(URL).order_by(func.random()).limit(1000).all()
    creation_times = [url.last_modified for url in urls]
    creation_times = [datetime.datetime.strptime(time, '%Y-%m-%d') 
                      for time in creation_times if time]
    creation_times = [time for time in creation_times 
                      if time >= datetime.datetime(2012, 1, 1)]
    sns.histplot(creation_times, bins=30)
    sns.despine()

plt.figure(figsize=(10, 6))
plot_creation_time()
plt.title('Last Modified Time of URLs (Sample of 1,000)')
plt.xlabel('Creation Time')
plt.ylabel('Frequency')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```

This generates a histogram showing the distribution of article publication dates:

![Publication Date Histogram](../assets/publication_date_histogram.png)

## Database Queries for Analysis

The Medium-Mining database schema is optimized for analytical queries. Here are some examples:

### Most Common Tags

```python
from sqlalchemy import func

# Query the most common tags
def get_most_common_tags(session, limit=20):
    # Extract individual tags from the comma-separated tag field
    articles = session.query(MediumArticle).all()
    
    # Extract and flatten tags
    tag_list = []
    for article in articles:
        if article.tags:
            tags = [tag.strip() for tag in article.tags.split(',')]
            tag_list.extend(tags)
    
    # Count and sort
    tag_counts = {}
    for tag in tag_list:
        if tag:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Convert to sorted list of tuples
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_tags[:limit]
```

### Articles with Most Claps

```python
# Query articles with the most claps
def get_most_clapped_articles(session, limit=10):
    # Convert claps to numeric and sort
    articles = session.query(MediumArticle).all()
    
    # Filter, convert claps to numeric, and sort
    parsed_articles = []
    for article in articles:
        try:
            if article.claps and article.claps.strip():
                # Remove commas and convert to int
                claps = int(article.claps.replace(',', ''))
                parsed_articles.append((article, claps))
        except (ValueError, AttributeError):
            continue
    
    # Sort by claps (descending)
    sorted_articles = sorted(parsed_articles, key=lambda x: x[1], reverse=True)
    return sorted_articles[:limit]
```

### Comment Distribution

```python
# Analyze comment distribution
def analyze_comment_distribution(session):
    # Query articles with their comment counts
    articles = session.query(MediumArticle).all()
    
    # Extract comment counts
    comment_counts = [article.comments_count for article in articles 
                      if article.comments_count is not None]
    
    # Calculate statistics
    stats = {
        'mean': np.mean(comment_counts),
        'median': np.median(comment_counts),
        'std_dev': np.std(comment_counts),
        'min': np.min(comment_counts),
        'max': np.max(comment_counts),
        'articles_with_comments': sum(1 for count in comment_counts if count > 0),
        'total_articles': len(comment_counts)
    }
    
    return stats, comment_counts
```

## Visualizations

The Medium-Mining data analysis tools support various visualizations:

### Word Clouds

Word clouds can be generated from article content to visualize frequent terms:

```python
from wordcloud import WordCloud

def generate_word_cloud(session, min_word_length=4, max_words=100):
    # Get article text
    articles = session.query(MediumArticle).all()
    
    # Combine text from all articles
    all_text = ' '.join([article.full_article_text for article in articles 
                          if article.full_article_text])
    
    # Generate word cloud
    wordcloud = WordCloud(
        width=800, 
        height=400, 
        background_color='white',
        min_word_length=min_word_length,
        max_words=max_words
    ).generate(all_text)
    
    # Display
    plt.figure(figsize=(16, 8))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.title('Most Common Words in Medium Articles')
    plt.show()
```

### Correlation Heatmaps

Correlation heatmaps can reveal relationships between different article metrics:

```python
def create_correlation_heatmap(session):
    # Extract article data
    articles = session.query(MediumArticle).all()
    
    # Create DataFrame with metrics
    data = []
    for article in articles:
        try:
            claps = int(article.claps.replace(',', '')) if article.claps else 0
            comments = article.comments_count or 0
            text_length = len(article.full_article_text) if article.full_article_text else 0
            
            # Calculate more metrics
            title_length = len(article.title) if article.title else 0
            tag_count = len(article.tags.split(',')) if article.tags else 0
            
            data.append({
                'claps': claps,
                'comments': comments,
                'text_length': text_length,
                'title_length': title_length,
                'tag_count': tag_count
            })
        except (ValueError, AttributeError):
            continue
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Calculate correlation matrix
    corr = df.corr()
    
    # Create heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr, annot=True, cmap='coolwarm', vmin=-1, vmax=1)
    plt.title('Correlation Between Article Metrics')
    plt.tight_layout()
    plt.show()
    
    return corr
```

## Integration with External Analysis Tools

The data collected by Medium-Mining can be exported for use with external analysis tools:

### Export to CSV

```python
def export_to_csv(session, filepath='medium_articles.csv'):
    # Query articles
    articles = session.query(MediumArticle).all()
    
    # Create list of dictionaries
    data = []
    for article in articles:
        data.append({
            'id': article.id,
            'title': article.title,
            'author': article.author_name,
            'published': article.date_published,
            'modified': article.date_modified,
            'claps': article.claps,
            'comments': article.comments_count,
            'tags': article.tags,
            'is_free': article.is_free,
            'publisher': article.publisher,
        })
    
    # Create DataFrame and export
    df = pd.DataFrame(data)
    df.to_csv(filepath, index=False)
    print(f"Exported {len(data)} articles to {filepath}")
    
    return df
```

### Export to JSON

```python
def export_to_json(session, filepath='medium_articles.json'):
    # Query articles
    articles = session.query(MediumArticle).all()
    
    # Create list of dictionaries
    data = []
    for article in articles:
        # Get comments for this article
        comments = session.query(Comment).filter(Comment.article_id == article.id).all()
        comment_data = [
            {
                'id': comment.id,
                'username': comment.username,
                'text': comment.text,
                'claps': comment.claps,
                'references_article': comment.references_article
            }
            for comment in comments
        ]
        
        # Create article data
        article_data = {
            'id': article.id,
            'title': article.title,
            'author': article.author_name,
            'published': article.date_published,
            'modified': article.date_modified,
            'claps': article.claps,
            'comments_count': article.comments_count,
            'tags': article.tags.split(',') if article.tags else [],
            'is_free': article.is_free,
            'publisher': article.publisher,
            'comments': comment_data
        }
        
        data.append(article_data)
    
    # Export to JSON
    import json
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Exported {len(data)} articles to {filepath}")
    
    return data
```

## Next Steps

- Explore the [Basic Analysis](basic-analysis.md) section for simple data analysis techniques
- Learn about [Content Analysis](content-analysis.md) for extracting insights from article text
- Check out [Temporal Analysis](temporal-analysis.md) for studying trends over time
- See [Export Data](export-data.md) for exporting data to various formats