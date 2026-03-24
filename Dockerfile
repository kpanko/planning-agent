FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies (no dev extras)
RUN uv sync --no-dev --frozen

# Copy source
COPY src/ ./src/

# Install the project itself
RUN uv pip install --no-deps -e .

# Data directory (override with PLANNING_AGENT_DATA_DIR)
RUN mkdir -p /data
ENV PLANNING_AGENT_DATA_DIR=/data

EXPOSE 8080

CMD ["uv", "run", "planning-agent-web"]
