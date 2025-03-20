from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DB_PATH = 'duckdb:///medium_articles.duckdb'  # Persistent storage
Base = declarative_base()

# Define ORM models
class Author(Base):
    __tablename__ = 'authors'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

class Sitemap(Base):
    __tablename__ = 'sitemaps'
    id = Column(Integer, primary_key=True)
    sitemap_url = Column(String(255), unique=True, nullable=False)
    articles_count = Column(Integer)

class URL(Base):
    __tablename__ = 'urls'
    id = Column(Integer, primary_key=True)
    url = Column(String(255), unique=True, nullable=False)
    last_modified = Column(String(50))
    change_freq = Column(String(50))
    priority = Column(Float)
    sitemap_id = Column(Integer, ForeignKey('sitemaps.id'))

class MediumArticle(Base):
    __tablename__ = 'medium_articles'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    author_id = Column(Integer, ForeignKey('authors.id'))
    url_id = Column(Integer, ForeignKey('urls.id'))
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

class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('medium_articles.id'))
    username = Column(String(100))
    text = Column(Text)
    date_posted = Column(String(50))

# Database setup functions
def setup_database(db_path=DB_PATH):
    """Set up the SQLAlchemy database and create tables."""
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    return engine

def get_session(db_path=DB_PATH):
    """Get a SQLAlchemy session for database operations."""
    engine = create_engine(db_path)
    Session = sessionmaker(bind=engine)
    return Session()

if __name__ == "__main__":
    # Set up the database
    engine = setup_database()