import requests
import time
import concurrent.futures
import json
import pandas as pd
from datetime import datetime, UTC

GITHUB_TOKEN = "YOUR_GITHUB_TOKEN"
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
API_BASE = "https://api.github.com"

MAX_PAGES = 5
MAX_WORKERS = 12
SCORE_THRESHOLD = 3


SEARCH_QUERIES = [
    '"chapters" "pages" language:JSON',
    '"groups" "chapters" language:JSON',
    '"series" "chapters" language:JSON',
    '"cubari" language:JSON',
    '"raw.githubusercontent.com" language:JSON',
]


# -----------------------------
# UTILITIES
# -----------------------------
def to_raw_url(html_url):
    return html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")


def extract_repo_from_url(raw_url):
    # https://raw.githubusercontent.com/user/repo/branch/file.json
    parts = raw_url.split("/")
    if len(parts) > 5:
        return f"{parts[3]}/{parts[4]}"
    return "unknown"


def github_search(query, page=1):
    url = f"{API_BASE}/search/code"
    params = {
        "q": query,
        "per_page": 100,
        "page": page
    }
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code == 200:
        return r.json()
    return {}


def get_repo_tree(repo_full_name):
    url = f"{API_BASE}/repos/{repo_full_name}/git/trees/HEAD?recursive=1"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        return r.json().get("tree", [])
    return []


def fetch_json(url):
    try:
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


REQUIRED_ROOT_FIELDS = {
    "title": str,
    "description": str,
    "artist": str,
    "author": str,
    "cover": str,
    "chapters": dict
}


def validate_root_schema(data):
    if not isinstance(data, dict):
        return False, "Root is not a dictionary"

    for field, field_type in REQUIRED_ROOT_FIELDS.items():
        if field not in data:
            return False, f"Missing required field: {field}"
        if not isinstance(data[field], field_type):
            return False, f"Invalid type for field: {field}"

    return True, None


def validate_chapters_structure(chapters):
    if not isinstance(chapters, dict) or not chapters:
        return False, "Chapters must be a non-empty dictionary"

    valid_chapter_count = 0

    for chapter_number, chapter_data in chapters.items():

        if not isinstance(chapter_data, dict):
            continue

        required_chapter_fields = ["title", "volume", "groups"]

        if not all(field in chapter_data for field in required_chapter_fields):
            continue

        if not isinstance(chapter_data["groups"], dict):
            continue

        # Validate groups
        valid_groups = 0
        for group_name, group_value in chapter_data["groups"].items():
            if isinstance(group_value, str) and group_value.strip():
                valid_groups += 1

        if valid_groups > 0:
            valid_chapter_count += 1

    if valid_chapter_count == 0:
        return False, "No valid chapters found"

    return True, None


def strict_validate_cubari(data):
    # Root validation
    valid_root, root_error = validate_root_schema(data)
    if not valid_root:
        return False, root_error

    # Chapters validation
    valid_chapters, chapter_error = validate_chapters_structure(data["chapters"])
    if not valid_chapters:
        return False, chapter_error

    return True, None


def validate_candidate(raw_url, source_type):
    data = fetch_json(raw_url)
    if not data:
        return None

    is_valid, error = strict_validate_cubari(data)

    if not is_valid:
        return None

    score = 0
    if data["cover"].startswith("http"):
        score += 1

    return {
        "title": data.get("title", ""),
        "cover": data.get("cover", ""),
        "url": raw_url,
        "repo": extract_repo_from_url(raw_url),
        "found_via": source_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "chapters_count": len(data["chapters"])
    }


# -----------------------------
# CODE SEARCH
# -----------------------------
def code_search_phase():
    candidates = []

    for query in SEARCH_QUERIES:
        print(f"Searching query: {query}")

        for page in range(1, MAX_PAGES + 1):
            results = github_search(query, page)
            if "items" not in results:
                break

            for item in results["items"]:
                raw_url = to_raw_url(item["html_url"])
                candidates.append((raw_url, "code_search"))

            time.sleep(0.5)

    return candidates


# -----------------------------
# REPO SCAN
# -----------------------------
def repo_scan_phase():
    repo_candidates = []

    repo_query = "cubari in:readme"
    for page in range(1, MAX_PAGES + 1):
        url = f"{API_BASE}/search/repositories"
        params = {
            "q": repo_query,
            "per_page": 50,
            "page": page
        }

        r = requests.get(url, headers=HEADERS, params=params)
        data = r.json()

        if "items" not in data:
            break

        for repo in data["items"]:
            full_name = repo["full_name"]
            tree = get_repo_tree(full_name)

            for file in tree:
                if file["path"].endswith(".json"):
                    raw_url = f"https://raw.githubusercontent.com/{full_name}/HEAD/{file['path']}"
                    repo_candidates.append((raw_url, "repo_scan"))

        time.sleep(0.5)

    return repo_candidates


# -----------------------------
# MAIN ENGINE
# -----------------------------
def run():
    print("Phase 1: Code Search")
    candidates = code_search_phase()

    print("Phase 2: Repo Scan")
    candidates.extend(repo_scan_phase())

    print(f"Total candidates before validation: {len(candidates)}")

    validated = []
    seen_urls = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []

        for raw_url, source_type in candidates:
            if raw_url not in seen_urls:
                seen_urls.add(raw_url)
                futures.append(
                    executor.submit(validate_candidate, raw_url, source_type)
                )

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                validated.append(result)
                print("✓ Found:", result["url"])

    # Save to CSV
    if validated:
        df = pd.DataFrame(validated)
        filename = f"cubari_sources_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False)
        print(f"\nSaved {len(validated)} results to {filename}")
    else:
        print("\nNo valid Cubari sources found.")

    # Optional JSON print
    print("\nJSON Preview:")
    print(json.dumps(validated[:10], indent=2))


if __name__ == "__main__":
    run()
