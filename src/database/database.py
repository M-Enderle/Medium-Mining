from sqlalchemy import (Column, Float, ForeignKey, Integer, Sequence, String,
                        Text, create_engine, DateTime)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "duckdb:///medium_articles.duckdb"  # Persistent storage
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Define ORM models
# Author model removed

class Sitemap(Base):
    __tablename__ = "sitemaps"
    sitemap_id_seq = Sequence("sitemap_id_seq")

    id = Column(
        "id",
        Integer,
        sitemap_id_seq,
        server_default=sitemap_id_seq.next_value(),
        primary_key=True,
    )
    sitemap_url = Column(String(255), unique=True, nullable=False)
    articles_count = Column(Integer)


class URL(Base):
    __tablename__ = "urls"
    url_id_seq = Sequence("url_id_seq")

    id = Column(
        "id",
        Integer,
        url_id_seq,
        server_default=url_id_seq.next_value(),
        primary_key=True,
    )
    url = Column(String(255), unique=True, nullable=False)
    last_modified = Column(String(50))
    change_freq = Column(String(50))
    priority = Column(Float)
    sitemap_id = Column(Integer, ForeignKey("sitemaps.id"))
    last_crawled = Column(DateTime, nullable=True)  # Already used in code
    crawl_status = Column(String(50), nullable=True)  # Already used in code
    last_scraped = Column(DateTime, nullable=True)  # New column to track scraping


class MediumArticle(Base):
    __tablename__ = "medium_articles"
    article_id_seq = Sequence("article_id_seq")

    id = Column(
        "id",
        Integer,
        article_id_seq,
        server_default=article_id_seq.next_value(),
        primary_key=True,
    )
    url_id = Column(Integer, ForeignKey("urls.id"))
    title = Column(String(255), nullable=False)
    author_name = Column(String(100))  # Changed from author_id to author_name
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
    comment_id_seq = Sequence("comment_id_seq")

    id = Column(
        "id",
        Integer,
        comment_id_seq,
        server_default=comment_id_seq.next_value(),
        primary_key=True,
    )
    article_id = Column(Integer, ForeignKey("medium_articles.id"))
    username = Column(String(100))
    text = Column(Text)
    date_posted = Column(String(50))


def get_session(db_path=DATABASE_URL):
    """Get a SQLAlchemy session for database operations."""
    return SessionLocal()


def setup_database():
    """Create the database and tables if they don't exist."""
    try:
        Base.metadata.create_all(engine)
        print("Database and tables created successfully.")
    except Exception as e:
        print(f"Error creating database: {e}")


if __name__ == "__main__":
    # Set up the database
    setup_database()
