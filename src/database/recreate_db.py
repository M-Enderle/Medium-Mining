from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import (  # replace this with the actual module name
    Base, Sitemap, URL, Author, MediumArticle, Comment
)

# Define paths
OLD_DB_URL = "duckdb:///medium_articles.duckdb"
NEW_DB_URL = "duckdb:///medium_articles_clean.duckdb"

# Set up SQLAlchemy engines/sessions
old_engine = create_engine(OLD_DB_URL)
new_engine = create_engine(NEW_DB_URL)

OldSession = sessionmaker(bind=old_engine)
NewSession = sessionmaker(bind=new_engine)

# Create all tables in the new DB
Base.metadata.create_all(new_engine)

# Helper to remove internal SQLAlchemy state
def safe_model_copy(instance, cls):
    return cls(**{
        k: v
        for k, v in vars(instance).items()
        if not k.startswith("_")
    })

def transfer_data():
    old_session = OldSession()
    new_session = NewSession()

    try:
        # Transfer Authors
        authors = old_session.query(Author).all()
        for a in authors:
            new_session.add(safe_model_copy(a, Author))
        new_session.commit()

        # Transfer Sitemaps
        sitemaps = old_session.query(Sitemap).all()
        for sm in sitemaps:
            new_session.add(safe_model_copy(sm, Sitemap))
        new_session.commit()

        # Transfer URLs (filtering null URLs)
        urls = old_session.query(URL).filter(URL.url != None).all()
        for u in urls:
            new_session.add(safe_model_copy(u, URL))
        new_session.commit()

        # Transfer Articles (filtering missing title or author)
        articles = old_session.query(MediumArticle).filter(
            MediumArticle.title != None,
            MediumArticle.author_id != None
        ).all()
        for a in articles:
            new_session.add(safe_model_copy(a, MediumArticle))
        new_session.commit()

        # Transfer Comments (only if full_text is present)
        comments = old_session.query(Comment).filter(
            Comment.full_text != None
        ).all()
        for c in comments:
            new_session.add(safe_model_copy(c, Comment))
        new_session.commit()

        print("✅ Data transfer complete.")
    except Exception as e:
        new_session.rollback()
        print(f"❌ Error during transfer: {e}")
    finally:
        old_session.close()
        new_session.close()

if __name__ == "__main__":
    transfer_data()