import sqlite3
import pandas as pd
import json
import glob
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DB_PATH = "cubari.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Enable foreign keys
    c.execute("PRAGMA foreign_keys = ON;")

    # Series Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            artist TEXT,
            author TEXT,
            cover TEXT,
            url TEXT UNIQUE NOT NULL,
            repo TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Chapters Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER,
            number TEXT,
            title TEXT,
            volume TEXT,
            group_name TEXT,
            url TEXT,
            FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE
        );
    """)

    # Full Text Search Table
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS series_fts USING fts5(
            title, description, author, artist,
            content='series', content_rowid='id'
        );
    """)

    # Finder Cache Table (for incremental scanning)
    c.execute("""
        CREATE TABLE IF NOT EXISTS finder_cache (
            url TEXT PRIMARY KEY,
            sha TEXT,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_valid BOOLEAN,
            source_type TEXT
        );
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_finder_cache_sha ON finder_cache(sha);")

    # ... Triggers ...

    conn.commit()
    conn.close()
    logger.info("Database initialized.")


def sanitize(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def index_latest_json():
    list_of_files = glob.glob("cubari_sources_*.json")
    if not list_of_files:
        logger.info("No JSON files found to index.")
        return

    latest_file = max(list_of_files, key=os.path.getctime)
    logger.info(f"Indexing {latest_file}...")

    with open(latest_file, "r") as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for item in data:
        try:
            # Upsert Series
            c.execute(
                """
                INSERT INTO series (title, description, artist, author, cover, url, repo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    artist=excluded.artist,
                    author=excluded.author,
                    cover=excluded.cover,
                    repo=excluded.repo,
                    last_updated=CURRENT_TIMESTAMP
                RETURNING id;
            """,
                (
                    sanitize(item.get("title", "")),
                    sanitize(item.get("description", "")),
                    sanitize(item.get("artist", "")),
                    sanitize(item.get("author", "")),
                    sanitize(item.get("cover", "")),
                    sanitize(item.get("url", "")),
                    sanitize(item.get("repo", "")),
                ),
            )

            series_id = c.fetchone()[0]

            # Upsert Chapters (Delete existing for simplicity on re-index)
            c.execute("DELETE FROM chapters WHERE series_id = ?", (series_id,))

            chapters = item.get("chapters", {})
            for chapter_num, chapter_data in chapters.items():
                if not isinstance(chapter_data, dict):
                    continue

                title = sanitize(chapter_data.get("title", ""))
                volume = sanitize(chapter_data.get("volume", ""))
                groups = chapter_data.get("groups", {})

                # Pick first group for simplicity or store all?
                # Storing multiple entries per chapter is better if multiple groups exist
                for group_name, group_url in groups.items():
                    c.execute(
                        """
                        INSERT INTO chapters (series_id, number, title, volume, group_name, url)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            series_id,
                            sanitize(chapter_num),
                            title,
                            volume,
                            sanitize(group_name),
                            sanitize(group_url),
                        ),
                    )

        except Exception as e:
            logger.error(f"Error indexing item {item.get('title')}: {e}")

    conn.commit()

    # Rebuild index to ensure FTS is populated
    logger.info("Rebuilding search index...")
    c.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild');")
    conn.commit()

    conn.close()
    logger.info("Indexing complete.")


if __name__ == "__main__":
    init_db()
    index_latest_json()
