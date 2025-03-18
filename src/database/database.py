from sqlalchemy import (REAL, Column, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Author(Base):
    __tablename__ = "authors"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    articles = relationship("MediumArticle", back_populates="article_author")


class URL(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True)
    url = Column(String(255), unique=True, nullable=False)
    last_modified = Column(String(50))
    change_freq = Column(String(50))
    priority = Column(REAL)
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
    title = Column(String(255), nullable=False)
    author_id = Column(Integer, ForeignKey("authors.id"))
    url_id = Column(Integer, ForeignKey("urls.id"))

    date_published = Column(String(50))
    last_modified = Column(String(50))
    last_crawled = Column(String(50))
    last_crawled_status = Column(String(50))
    exists = Column(String(50))
    description = Column(Text)
    publisher = Column(String(100))
    is_free = Column(String(50))
    claps = Column(String(20))
    comments_count = Column(Integer)
    tags = Column(String(255))
    full_article_text = Column(Text)

    # Relationships
    article_author = relationship("Author", back_populates="articles")
    article_url = relationship("URL", back_populates="medium_article")
    comments = relationship("Comment", order_by="Comment.id", back_populates="article")


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("medium_articles.id"))
    username = Column(String(100))
    text = Column(Text)
    date_posted = Column(String(50))

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
