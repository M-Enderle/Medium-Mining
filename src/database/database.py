from sqlalchemy import (
    REAL,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

DATABASE_URL = "sqlite+aiosqlite:///medium_mining.db"  # Corrected database URL

Base = declarative_base()
async_engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)


class URL(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True)
    url = Column(String(255), unique=True, nullable=False)
    last_modified = Column(String(50))
    change_freq = Column(String(50))
    priority = Column(REAL)
    last_crawled = Column(DateTime)
    crawl_status = Column(String(255))
    sitemap_id = Column(Integer, ForeignKey("sitemaps.id"))  # Added foreign key

    # Relationships
    medium_article = relationship("MediumArticle", back_populates="article_url")
    sitemap = relationship("Sitemap", back_populates="urls")

    def __repr__(self):
        return f"<URL(id={self.id}, url='{self.url}', last_modified='{self.last_modified}', change_freq='{self.change_freq}', priority={self.priority})>"

    def __str__(self):
        return self.__repr__()


class Sitemap(Base):
    __tablename__ = "sitemaps"
    id = Column(Integer, primary_key=True)
    sitemap_url = Column(String(255), unique=True, nullable=False)
    articles_count = Column(Integer)
    # Relationships
    urls = relationship("URL", back_populates="sitemap")  # Single relationship to URL

    def __repr__(self):
        return f"<Sitemap(id={self.id}, sitemap_url='{self.sitemap_url}', articles_count={self.articles_count})>"

    def __str__(self):
        return self.__repr__()


class MediumArticle(Base):
    __tablename__ = "medium_articles"
    id = Column(Integer, primary_key=True)
    url_id = Column(Integer, ForeignKey("urls.id"))

    title = Column(String(255), nullable=False)
    author_name = Column(String(100))
    date_published = Column(String(50))
    date_modified = Column(String(50))
    description = Column(Text)
    publisher = Column(String(100))
    is_free = Column(String(50))
    claps = Column(String(20))
    comments_count = Column(Integer)
    tags = Column(String(255))
    full_article_text = Column(Text)

    # Relationships
    article_url = relationship("URL", back_populates="medium_article")
    comments = relationship("Comment", order_by="Comment.id", back_populates="article")


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("medium_articles.id"))
    username = Column(String(100))
    text = Column(Text)
    claps = Column(String(20))
    full_html_text = Column(Text)
    references_article = Column(Boolean)

    article = relationship("MediumArticle", back_populates="comments")


async def setup_database():
    """Create the database and tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():  # Changed to async
    async with AsyncSessionLocal() as session:  # Use async context manager
        yield session


if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_database())