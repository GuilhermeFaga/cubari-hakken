FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
# We don't strictly need uv here unless we want to use it for installation, 
# but pip is fine for a simple container.
# However, let's install the dependencies directly from pyproject.toml if possible, 
# or just manually install them for now since the file is simple.
# Better approach: generate requirements.txt or just install .
RUN pip install --no-cache-dir .

# Install additional dev/runtime dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic-settings \
    python-dotenv \
    httpx \
    beautifulsoup4

# Copy application code
COPY . .

# Default command (can be overridden by docker-compose)
CMD ["python", "main.py"]
