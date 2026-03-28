FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app/ ./app/

RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir ".[prod]"

COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY alembic.ini ./

EXPOSE 8000

CMD ["python", "-m", "app.main"]
