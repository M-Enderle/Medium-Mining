import duckdb
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Source database URL (replace with your actual source URL)
SOURCE_DATABASE_URL = "duckdb:///medium_articles_full.duckdb"
# Destination database URL (using the one from database.py)
DESTINATION_DATABASE_URL = "duckdb:///medium_articles.duckdb"

# Chunk size for reading data (adjust based on your memory constraints)
CHUNK_SIZE = 100000

def transfer_data(source_url, destination_url, chunk_size):
    """Transfers data from source DuckDB to destination DuckDB in chunks."""

    # Create SQLAlchemy engines for both databases
    source_engine = create_engine(source_url)
    dest_engine = create_engine(destination_url)

    # Create sessions
    SourceSession = sessionmaker(bind=source_engine)
    DestSession = sessionmaker(bind=dest_engine)
    source_session = SourceSession()
    dest_session = DestSession()

    try:
        # Transfer Sitemaps
        offset = 0
        while True:
            sitemaps = source_session.execute(text("SELECT id, sitemap_url, articles_count FROM sitemaps ORDER BY id LIMIT :limit OFFSET :offset"),
                                            {"limit": chunk_size, "offset": offset}).fetchall()
            if not sitemaps:
                break

            for sitemap in sitemaps:
                dest_session.execute(text("INSERT INTO sitemaps (id, sitemap_url, articles_count) VALUES (:id, :sitemap_url, :articles_count)"),
                                    {"id": sitemap[0], "sitemap_url": sitemap[1], "articles_count": sitemap[2]})
            
            dest_session.commit()
            offset += chunk_size
            print(f"Transferred Sitemaps: {offset}")

        # Transfer URLs
        offset = 0
        while True:
            urls = source_session.execute(text("SELECT id, url, last_modified, change_freq, priority, sitemap_id FROM urls ORDER BY id LIMIT :limit OFFSET :offset"),
                                        {"limit": chunk_size, "offset": offset}).fetchall()
            if not urls:
                break

            for url in urls:
                dest_session.execute(text("INSERT INTO urls (id, url, last_modified, change_freq, priority, sitemap_id) VALUES (:id, :url, :last_modified, :change_freq, :priority, :sitemap_id)"),
                                    {"id": url[0], "url": url[1], "last_modified": url[2], "change_freq": url[3], "priority": url[4], "sitemap_id": url[5]})

            dest_session.commit()
            offset += chunk_size
            print(f"Transferred URLs: {offset}")

    except Exception as e:
        print(f"An error occurred: {e}")
        dest_session.rollback()
    finally:
        source_session.close()
        dest_session.close()

if __name__ == "__main__":
    transfer_data(SOURCE_DATABASE_URL, DESTINATION_DATABASE_URL, CHUNK_SIZE)
    print("Data transfer complete.")
