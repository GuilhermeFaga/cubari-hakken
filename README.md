# Cubari GitHub Source Finder

A high-confidence discovery engine for finding **Cubari-compatible manga sources** hosted on GitHub.

This tool:

* 🔍 Searches GitHub using structural queries (not filename-based)
* 📂 Scans repositories recursively
* 🧠 Validates strict Cubari schema
* ⚡ Uses parallel validation
* 📊 Exports results to CSV
* 🧹 Deduplicates and ranks findings

---

## Features

### Smart Discovery

* Multiple structural search queries
* Repo-level scanning for Cubari mentions
* Recursive JSON tree scanning
* No filename dependency

### Strict Schema Validation

Only accepts JSON files that match this required structure:

```json
{
  "title": "<manga title>",
  "description": "<manga description>",
  "artist": "<manga artist>",
  "author": "<manga author>",
  "cover": "<mangacoverurl.jpg>",
  "chapters": {
    "<chapter number>": {
      "title": "<chapter name>",
      "volume": "<volume number>",
      "groups": {
        "<group name>": "/proxy/api/imgur/chapter/<imgur id>/"
      },
      "last_updated": "1616368746"
    }
  }
}
```

### Validation Rules

✔ Must contain all required top-level fields
✔ All required fields must have correct data types
✔ `chapters` must be a non-empty dictionary
✔ At least one valid chapter must exist
✔ Chapter must contain:

* `title`
* `volume`
* `groups`
* At least one valid group entry

Files that do not match are rejected.

---

## Output

Results are exported as a timestamped CSV file:

```
cubari_sources_YYYYMMDD_HHMMSS.csv
```

### CSV Columns

| Column         | Description                 |
| -------------- | --------------------------- |
| url            | Raw GitHub JSON URL         |
| repo           | GitHub repository           |
| score          | Validation confidence score |
| found_via      | Discovery method            |
| timestamp      | UTC discovery time          |
| chapters_count | Number of chapters found    |

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd cubari-finder
```

### 2. Install dependencies

```bash
uv sync
```

---

## GitHub Token (Required)

You need a GitHub Personal Access Token to avoid heavy rate limits.

Create one here:
[https://github.com/settings/tokens](https://github.com/settings/tokens)

Then edit the script:

```python
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN"
```

Recommended scopes:

* public_repo

---

## Usage

```bash
uv run python cubari_finder.py
```

The tool will:

1. Run code search queries
2. Scan repositories mentioning Cubari
3. Recursively inspect JSON files
4. Strictly validate schema
5. Export valid findings to CSV

---

## How It Works

### Phase 1 — Code Search

Uses GitHub Search API with structural JSON queries like:

* `"chapters" "pages" language:JSON`
* `"groups" "chapters" language:JSON`
* `"series" "chapters" language:JSON`

### Phase 2 — Repository Scan

Searches for repositories mentioning "cubari" in README.

Then:

* Retrieves full repository tree
* Recursively finds all JSON files
* Validates them locally

### Phase 3 — Strict Validation

Schema-aware validation ensures:

* Required root fields exist
* Correct data types
* Valid chapter structure
* At least one valid group

Only fully valid Cubari sources are accepted.

---

## Performance

* Parallel validation using ThreadPoolExecutor
* Deduplicated URL processing
* Rate-limit safe with small delays
* Configurable worker count

---

## Configuration

Inside the script:

```python
MAX_PAGES = 5
MAX_WORKERS = 12
SCORE_THRESHOLD = 3
```

You can increase pages and workers for more aggressive scanning.

---

## Limitations

* GitHub API rate limits apply
* Only default branch is scanned
* GitHub search API caps at 1000 results per query
* Private repositories are not accessible
* Some sources may not be indexed

---

## Future Improvements (Optional)

* SQLite local index
* Incremental daily scanning
* GitHub GraphQL integration
* BigQuery GitHub Archive scanning
* Web dashboard interface
* Auto Cubari compatibility testing
* Continuous crawler mode

---


## Disclaimer

This tool only indexes publicly available GitHub content.
It does not host, proxy, or redistribute any media.

Use responsibly.

This tools was vibe coded.