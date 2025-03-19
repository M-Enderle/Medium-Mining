from sqlalchemy import REAL, Column, ForeignKey, Integer, String, Text, create_engine, DateTime, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class URL(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True)
    url = Column(String(255), unique=True, nullable=False)
    last_modified = Column(String(50))
    change_freq = Column(String(50))
    priority = Column(REAL)
    crawled = Column(Boolean, default=False)  # Added crawled column
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

    last_crawled = Column(DateTime)
    crawl_status = Column(String(50))

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


def setup_database(db_path="sqlite:///medium_articles.db"):
    """Set up the database and return engine and session factory."""
    engine = create_engine(db_path, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


def get_session(db_path="sqlite:///medium_articles.db"):
    """Get a new session for database operations."""
    engine, Session = setup_database(db_path)
    session = Session()
    return session


if __name__ == "__main__":
    setup_database()
