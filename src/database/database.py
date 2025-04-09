from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    create_engine,
    Date,
    SmallInteger,
    Numeric,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

DATABASE_URL = "duckdb:///medium_articles.duckdb"  # Persistent storage
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    articles_count = Column(SmallInteger, nullable=True)

    urls = relationship("URL", back_populates="sitemap")


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
    last_modified = Column(Date, nullable=True)
    change_freq = Column(SmallInteger, nullable=True)
    priority = Column(Numeric(precision=5, scale=1), nullable=True)
    sitemap_id = Column(Integer, ForeignKey("sitemaps.id"), nullable=True)
    last_crawled = Column(DateTime, nullable=True)
    crawl_status = Column(String(12), nullable=True)
    crawl_failure_reason = Column(String(255), nullable=True)
    found_on_url_id = Column(Integer, ForeignKey("urls.id"), nullable=True)

    found_on_url = relationship("URL", remote_side=[id], backref="found_urls")
    sitemap = relationship("Sitemap", back_populates="urls")
    articles = relationship("MediumArticle", back_populates="url")


class Author(Base):
    __tablename__ = "authors"
    author_id_seq = Sequence("author_id_seq")

    id = Column(
        "id",
        Integer,
        author_id_seq,
        server_default=author_id_seq.next_value(),
        primary_key=True,
    )
    username = Column(String(100), nullable=True, unique=True)
    medium_url = Column(String(255), nullable=True, unique=True)
    articles = relationship("MediumArticle", back_populates="author")
    comments = relationship("Comment", back_populates="author")


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
    author_id = Column(Integer, ForeignKey("authors.id"), nullable=False)
    date_published = Column(DateTime, nullable=True)
    date_modified = Column(DateTime, nullable=True)
    date_created = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    publisher_type = Column(String(50), nullable=True)
    is_free = Column(Boolean, nullable=True)
    claps = Column(Integer, nullable=True)
    comments_count = Column(SmallInteger, nullable=True)
    full_article_text = Column(Text, nullable=True)
    read_time = Column(SmallInteger, nullable=True)
    type = Column(String(50), nullable=True)

    tags = Column(ARRAY(String), nullable=True)
    author = relationship("Author", back_populates="articles")
    comments = relationship("Comment", back_populates="article")
    url = relationship("URL", back_populates="articles")


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
    author_id = Column(Integer, ForeignKey("authors.id"), nullable=True)
    text = Column(Text, nullable=True)
    full_text = Column(Text, nullable=False)
    claps = Column(SmallInteger, nullable=True)
    references_article = Column(Boolean, nullable=False)
    author = relationship("Author", back_populates="comments")
    article = relationship("MediumArticle", back_populates="comments")


def get_session():
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
    setup_database()
