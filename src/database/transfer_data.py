import sqlite3
from database import (Base, SessionLocal, Sitemap, URL, create_engine,
                               setup_database, sessionmaker)
from tqdm import tqdm

# Database file path
DATABASE_PATH = 'medium_articles.db'  # Replace with your desired database file

def connect_to_db():
    """Connects to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        print("Connected to database successfully")
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return None
    

def print_table_names(conn):
    """Prints the names of all tables in the database."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables in the database:")
        for table in tables:
            print(table[0])
    except sqlite3.Error as e:
        print(f"Error fetching table names: {e}")

def print_table_columns(conn, table_name):
    """Prints all columns in a specified table."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print(f"Columns in table '{table_name}':")
        for column in columns:
            # column[1] is the column name, column[2] is the data type
            print(f"  {column[1]} ({column[2]})")
    except sqlite3.Error as e:
        print(f"Error fetching column information: {e}")


def transfer_data():
    """Transfers data from SQLite to DuckDB with a progress bar."""
    sqlite_conn = connect_to_db()
    if not sqlite_conn:
        print("Aborting data transfer due to SQLite connection failure.")
        return

    duckdb_engine = create_engine("duckdb:///medium_articles.duckdb", echo=False)
    Base.metadata.create_all(duckdb_engine)
    DuckDB_Session = sessionmaker(bind=duckdb_engine)
    duckdb_session = DuckDB_Session()

    try:
        # Transfer Sitemaps
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT id, sitemap_url, articles_count FROM sitemaps")
        sitemaps = sqlite_cursor.fetchall()

        with tqdm(total=len(sitemaps), desc="Transferring Sitemaps") as pbar:
            for sitemap in sitemaps:
                sitemap_id, sitemap_url, articles_count = sitemap
                new_sitemap = Sitemap(
                    id=sitemap_id, sitemap_url=sitemap_url, articles_count=articles_count
                )
                duckdb_session.add(new_sitemap)
                pbar.update(1)

        # Transfer URLs in batches
        sqlite_cursor.execute("SELECT COUNT(*) FROM urls")
        total_urls = sqlite_cursor.fetchone()[0]
        batch_size = 100000
        offset = 0

        with tqdm(total=total_urls, desc="Transferring URLs") as pbar:
            while offset < total_urls:
                sqlite_cursor.execute(
                    "SELECT id, url, last_modified, change_freq, priority, sitemap_id FROM urls LIMIT ? OFFSET ?",
                    (batch_size, offset),
                )
                urls = sqlite_cursor.fetchall()

                for url in urls:
                    (
                        url_id,
                        url_value,
                        last_modified,
                        change_freq,
                        priority,
                        sitemap_id,
                    ) = url
                    new_url = URL(
                        id=url_id,
                        url=url_value,
                        last_modified=last_modified,
                        change_freq=change_freq,
                        priority=priority,
                        sitemap_id=sitemap_id,
                    )
                    duckdb_session.add(new_url)
                    pbar.update(1)

                duckdb_session.commit()  # Commit after each batch
                offset += batch_size

        print("Data transfer completed successfully.")

    except sqlite3.Error as e:
        print(f"Error during data transfer: {e}")
        duckdb_session.rollback()
    finally:
        sqlite_conn.close()
        duckdb_session.close()


# Example usage:
if __name__ == "__main__":
    # setup_database()  # Ensure DuckDB database and tables are created
    transfer_data()
    connection = connect_to_db()
    if connection:
        print_table_names(connection)
        print_table_columns(connection, "urls")
        print_table_columns(connection, "sitemaps")
        connection.close()  # Close the connection when done
        print("Connection closed.")
