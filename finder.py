import os
import time
import json
import logging
import concurrent.futures
import requests
import sqlite3
import pandas as pd
from datetime import datetime, UTC
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List, Optional, Set, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Configuration ---
class Settings(BaseSettings):
    github_tokens: str = Field(default="", alias="GITHUB_TOKEN")
    search_query: str = Field(default='"chapters" extension:json', alias="SEARCH_QUERY")
    max_workers: int = Field(default=12, alias="MAX_WORKERS")
    db_path: str = "cubari.db"
    api_base: str = "https://api.github.com"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()


# --- Database / Cache ---
class CacheManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        # Ensure table exists (indexer should have created it, but good for safety)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS finder_cache (
                url TEXT PRIMARY KEY,
                sha TEXT,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_valid BOOLEAN,
                source_type TEXT
            );
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_finder_cache_sha ON finder_cache(sha);"
        )
        conn.commit()
        conn.close()

    def is_sha_cached(self, sha: str) -> bool:
        if not sha:
            return False
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM finder_cache WHERE sha = ?", (sha,))
        result = c.fetchone()
        conn.close()
        return result is not None

    def save_result(self, url: str, sha: str, is_valid: bool, source_type: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute(
                """
                INSERT INTO finder_cache (url, sha, is_valid, source_type, last_checked)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(url) DO UPDATE SET
                    sha=excluded.sha,
                    is_valid=excluded.is_valid,
                    last_checked=CURRENT_TIMESTAMP
            """,
                (url, sha, is_valid, source_type),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Cache write error: {e}")
        finally:
            conn.close()


cache_manager = CacheManager(settings.db_path)


# --- Token Management ---
class TokenManager:
    def __init__(self, token_string: str):
        # Support comma-separated tokens
        raw_tokens = [t.strip() for t in token_string.split(",") if t.strip()]
        if not raw_tokens:
            raise ValueError("No GitHub tokens provided.")

        self.tokens = raw_tokens
        self.current_index = 0
        self.last_failure_time = 0

    def get_token(self) -> str:
        return self.tokens[self.current_index]

    def report_rate_limit(self):
        logger.warning(f"Token {self.current_index} rate limited. Switching...")
        self.current_index = (self.current_index + 1) % len(self.tokens)

        # If we cycled back to 0 immediately (only 1 token), we must sleep
        if len(self.tokens) == 1:
            logger.info("Only 1 token available. Sleeping 60s.")
            time.sleep(60)
        else:
            # If we just cycled through ALL tokens quickly, we should probably sleep
            # But for now, simple round-robin is usually enough unless all are exhausted
            pass


token_manager = TokenManager(settings.github_tokens)


# --- Utilities ---
def to_raw_url(html_url: str) -> str:
    return html_url.replace("github.com", "raw.githubusercontent.com").replace(
        "/blob/", "/"
    )


def extract_repo_info(raw_url: str) -> Optional[Dict[str, str]]:
    # https://raw.githubusercontent.com/user/repo/branch/path
    try:
        parts = raw_url.replace("https://raw.githubusercontent.com/", "").split("/")
        if len(parts) >= 3:
            return {
                "owner": parts[0],
                "repo": parts[1],
                "branch": parts[2],
                "path": "/".join(parts[3:]),
            }
    except Exception:
        pass
    return None


# --- Validation Logic (Reused) ---
def validate_root_schema(data: Any) -> tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Root is not a dictionary"
    if "title" not in data or "chapters" not in data:
        return False, "Missing title or chapters"
    if not isinstance(data["chapters"], dict):
        return False, "Chapters is not a dict"
    return True, None


def validate_chapters_structure(chapters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    if not chapters:
        return False, "Chapters empty"
    valid_chapter_count = 0
    for _, chapter_data in chapters.items():
        if not isinstance(chapter_data, dict):
            continue
        if "groups" in chapter_data and isinstance(chapter_data["groups"], dict):
            valid_groups = 0
            for _, group_value in chapter_data["groups"].items():
                if isinstance(group_value, str) and group_value.strip():
                    valid_groups += 1
            if valid_groups > 0:
                valid_chapter_count += 1
    if valid_chapter_count == 0:
        return False, "No valid chapters found"
    return True, None


def strict_validate_cubari(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    valid_root, root_error = validate_root_schema(data)
    if not valid_root:
        return False, root_error
    valid_chapters, chapter_error = validate_chapters_structure(data["chapters"])
    if not valid_chapters:
        return False, chapter_error
    return True, None


def fetch_json(url: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def validate_candidate(
    raw_url: str, source_type: str, sha: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    # Check cache first if SHA is provided
    if sha and cache_manager.is_sha_cached(sha):
        pass

    data = fetch_json(raw_url)
    if not data:
        if sha is not None:
            cache_manager.save_result(raw_url, sha, False, source_type)
        return None

    is_valid, error = strict_validate_cubari(data)

    if sha is not None:
        cache_manager.save_result(raw_url, sha, is_valid, source_type)

    if not is_valid:
        return None

    score = 0
    if data.get("cover", "").startswith("http"):
        score += 1

    repo_info = extract_repo_info(raw_url)
    return {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "artist": data.get("artist", ""),
        "author": data.get("author", ""),
        "cover": data.get("cover", ""),
        "url": raw_url,
        "repo": repo_info.get("repo") if repo_info else "unknown",
        "found_via": source_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "chapters_count": len(data.get("chapters", {})),
        "chapters": data.get("chapters", {}),
        "score": score,
    }


# --- API Interaction ---
def github_api_get(
    url: str, params: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token_manager.get_token()}"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)

        if r.status_code == 200:
            return r.json()

        if r.status_code in [403, 429]:
            token_manager.report_rate_limit()
            # Retry once with new token
            headers = {"Authorization": f"Bearer {token_manager.get_token()}"}
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()

        logger.warning(f"API {r.status_code} for {url}")
        return None
    except Exception as e:
        logger.error(f"API Request failed: {e}")
        return None


def deep_scan_repo(owner: str, repo: str) -> List[tuple]:
    """
    Fetches the recursive git tree of a repo and finds all .json files.
    Returns list of (raw_url, sha, source_type)
    """
    logger.info(f"Deep scanning {owner}/{repo}...")
    url = f"{settings.api_base}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"

    data = github_api_get(url)
    if data is None:
        return []

    if data.get("truncated"):
        logger.warning(f"Tree truncated for {owner}/{repo}")

    found = []
    tree = data.get("tree", [])
    for item in tree:
        path = item.get("path", "")
        if path.endswith(".json") and item.get("type") == "blob":
            sha = item.get("sha")
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"

            if sha and not cache_manager.is_sha_cached(sha):
                found.append((raw_url, "deep_scan", sha))

    return found


# --- Search Logic ---
def search_size_range(min_size: int, max_size: int, collected: List[tuple]):
    BASE_QUERY = settings.search_query
    query = f"{BASE_QUERY} size:{min_size}..{max_size}"

    data = github_api_get(
        f"{settings.api_base}/search/code",
        {"q": query, "per_page": 100, "sort": "indexed", "order": "desc"},
    )

    if not data or "total_count" not in data:
        return

    total = data["total_count"]
    logger.info(f"Range {min_size}..{max_size}: {total} results")

    if total == 0:
        return

    if total <= 1000:
        items = data.get("items", [])
        for item in items:
            sha = item["sha"]
            if not cache_manager.is_sha_cached(sha):
                raw_url = to_raw_url(item["html_url"])
                collected.append((raw_url, "search_shard", sha))
    else:
        mid = (min_size + max_size) // 2
        if mid == min_size:
            return
        search_size_range(min_size, mid, collected)
        search_size_range(mid + 1, max_size, collected)


def run():
    logger.info("Phase 1: Search Discovery")
    candidates = []

    # 1. Broad Search with Size Sharding
    # We scan 100B to 500KB
    search_size_range(100, 500000, candidates)

    logger.info(f"Found {len(candidates)} new candidates from search. Validating...")

    valid_results = []
    repos_to_scan = set()

    # 2. Validate Search Results
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.max_workers
    ) as executor:
        futures = {
            executor.submit(validate_candidate, url, src, sha): (url, sha)
            for url, src, sha in candidates
        }

        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_results.append(res)
                logger.info(f"✓ Valid: {res['title']}")
                # Mark repo for deep scan
                repo_info = extract_repo_info(res["url"])
                if repo_info:
                    repos_to_scan.add(f"{repo_info['owner']}/{repo_info['repo']}")

    # 3. Deep Scan
    logger.info(f"Phase 2: Deep Scan of {len(repos_to_scan)} repositories")
    deep_candidates = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.max_workers
    ) as executor:
        # Fetch trees in parallel
        future_to_repo = {
            executor.submit(deep_scan_repo, *repo.split("/")): repo
            for repo in repos_to_scan
        }

        for future in concurrent.futures.as_completed(future_to_repo):
            try:
                found = future.result()
                deep_candidates.extend(found)
            except Exception as e:
                logger.error(f"Deep scan error: {e}")

    logger.info(
        f"Found {len(deep_candidates)} new candidates from deep scan. Validating..."
    )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.max_workers
    ) as executor:
        futures = {
            executor.submit(validate_candidate, url, src, sha): (url, sha)
            for url, src, sha in deep_candidates
        }

        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_results.append(res)
                logger.info(f"✓ Deep Valid: {res['title']}")

    # 4. Save Output
    if valid_results:
        filename = f"cubari_sources_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
        df = pd.DataFrame(valid_results)
        df.to_csv(filename, index=False)

        json_filename = filename.replace(".csv", ".json")
        with open(json_filename, "w") as f:
            json.dump(valid_results, f, indent=2)

        logger.info(f"Saved {len(valid_results)} results to {filename}")
    else:
        logger.info("No valid results found this run.")


if __name__ == "__main__":
    run()
