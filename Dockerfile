FROM python:3.10-slim

WORKDIR /app

# System deps — cached as long as this layer doesn't change
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv via official installer (faster than pip install uv)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only dependency files first so this layer is cached
# and only re-runs when pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

# Copy application code
COPY src/ ./src/
COPY app/ ./app/
COPY api/ ./api/

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/vectors /app/data/audit_logs

EXPOSE 8501 8000

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data
ENV VECTOR_STORE_DIR=/app/data/vectors
ENV CHAT_HISTORY_DB=/app/data/chat_history.db

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health')" || exit 1

CMD ["uv", "run", "streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
