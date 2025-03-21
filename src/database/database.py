import duckdb
from sqlalchemy import (Column, Float, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "duckdb:///medium_articles.duckdb"  # Persistent storage
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Define ORM models
class Author(Base):
    __tablename__ = "authors"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    articles_count = Column(Integer)


class Sitemap(Base):
    __tablename__ = "sitemaps"
    id = Column(Integer, primary_key=True)
    sitemap_url = Column(String(255), unique=True, nullable=False)
    articles_count = Column(Integer)


class URL(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True)
    url = Column(String(255), unique=True, nullable=False)
    last_modified = Column(String(50))
    change_freq = Column(String(50))
    priority = Column(Float)
    sitemap_id = Column(Integer, ForeignKey("sitemaps.id"))


class MediumArticle(Base):
    __tablename__ = "medium_articles"
    id = Column(Integer, primary_key=True)
    url_id = Column(Integer, ForeignKey("urls.id"))
    title = Column(String(255), nullable=False)
    author_id = Column(Integer, ForeignKey("authors.id"))
    date_published = Column(String(50))
    date_modified = Column(String(50))
    description = Column(Text)
    publisher = Column(String(100))
    is_free = Column(String(50))
    claps = Column(String(20))
    comments_count = Column(Integer)
    tags = Column(String(255))
    full_article_text = Column(Text)


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("medium_articles.id"))
    username = Column(String(100))
    text = Column(Text)
    date_posted = Column(String(50))


# Database setup functions
def setup_database(db_path=DATABASE_URL):
    """Set up the SQLAlchemy database and create tables."""
    # Use raw DuckDB connection for table creation
    conn = duckdb.connect("medium_articles.duckdb")

    # Create tables with DuckDB-specific syntax
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS authors (
        id INTEGER PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        articles_count INTEGER
    )
    """
    )

    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS sitemaps (
        id INTEGER PRIMARY KEY,
        sitemap_url VARCHAR(255) UNIQUE NOT NULL,
        articles_count INTEGER
    )
    """
    )

    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS urls (
        id INTEGER PRIMARY KEY,
        url VARCHAR(255) UNIQUE NOT NULL,
        last_modified VARCHAR(50),
        change_freq VARCHAR(50),
        priority FLOAT,
        sitemap_id INTEGER,
        FOREIGN KEY (sitemap_id) REFERENCES sitemaps(id)
    )
    """
    )

    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS medium_articles (
        id INTEGER PRIMARY KEY,
        url_id INTEGER,
        title VARCHAR(255) NOT NULL,
        author_id INTEGER,
        date_published VARCHAR(50),
        date_modified VARCHAR(50),
        description TEXT,
        publisher VARCHAR(100),
        is_free VARCHAR(50),
        claps VARCHAR(20),
        comments_count INTEGER,
        tags VARCHAR(255),
        full_article_text TEXT,
        FOREIGN KEY (url_id) REFERENCES urls(id),
        FOREIGN KEY (author_id) REFERENCES authors(id)
    )
    """
    )

    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY,
        article_id INTEGER,
        username VARCHAR(100),
        text TEXT,
        date_posted VARCHAR(50),
        FOREIGN KEY (article_id) REFERENCES medium_articles(id)
    )
    """
    )

    conn.close()
    return engine


def get_session(db_path=DATABASE_URL):
    """Get a SQLAlchemy session for database operations."""
    return SessionLocal()


if __name__ == "__main__":
    # Set up the database
    setup_database()
