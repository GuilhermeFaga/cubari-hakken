from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import sqlite3
from typing import List, Optional
from pydantic import BaseModel
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cubari Hakken")

DB_PATH = "cubari.db"


class Chapter(BaseModel):
    number: str
    title: str
    volume: str
    group_name: str
    url: str


class Series(BaseModel):
    id: int
    title: str
    description: str
    artist: str
    author: str
    cover: str
    url: str
    repo: str
    chapters_count: Optional[int] = 0


class SeriesDetail(Series):
    chapters: List[Chapter]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/search", response_model=List[Series])
async def search(
    q: Optional[str] = Query(None, min_length=2), limit: int = 50, offset: int = 0
):
    conn = get_db()
    cursor = conn.cursor()

    try:
        # If no query string, return all series alphabetically
        if not q or not q.strip():
            cursor.execute(
                """
                SELECT s.*, (SELECT COUNT(*) FROM chapters WHERE series_id = s.id) as chapters_count
                FROM series s
                ORDER BY s.title ASC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )
        else:
            # Use FTS5 match
            # Format query for FTS5 (e.g. "romance" -> "romance*")
            # robust search: split by space, quote each term, append wildcard
            terms = q.strip().split()
            if not terms:
                return []

            # Escape quotes in terms and add wildcards
            fts_query = " ".join(f'"{term.replace('"', "")}"*' for term in terms)

            cursor.execute(
                """
                SELECT s.*, (SELECT COUNT(*) FROM chapters WHERE series_id = s.id) as chapters_count
                FROM series s
                JOIN series_fts fts ON s.id = fts.rowid
                WHERE series_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
            """,
                (fts_query, limit, offset),
            )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=400, detail="Invalid search query")
    finally:
        conn.close()


@app.get("/api/series/{series_id}", response_model=SeriesDetail)
async def get_series(series_id: int):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM series WHERE id = ?", (series_id,))
    series_row = cursor.fetchone()

    if not series_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Series not found")

    series_data = dict(series_row)

    cursor.execute(
        """
        SELECT number, title, volume, group_name, url 
        FROM chapters 
        WHERE series_id = ?
        ORDER BY CAST(number AS FLOAT) DESC
    """,
        (series_id,),
    )

    chapters_rows = cursor.fetchall()
    series_data["chapters"] = [dict(row) for row in chapters_rows]

    conn.close()
    return series_data


@app.get("/api/stats")
async def stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM series")
    series_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM chapters")
    chapters_count = cursor.fetchone()[0]
    conn.close()
    return {"series": series_count, "chapters": chapters_count}


# Mount static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
