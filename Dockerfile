FROM node:24-slim AS frontend

WORKDIR /frontend

ENV npm_config_fetch_retries=5 \
    npm_config_fetch_retry_factor=2 \
    npm_config_fetch_retry_mintimeout=20000 \
    npm_config_fetch_retry_maxtimeout=120000

COPY app/webapp/frontend/package.json app/webapp/frontend/package-lock.json ./
RUN npm ci --no-audit --prefer-offline

COPY app/webapp/frontend/ ./
RUN npm run build


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
COPY --from=frontend /dist/ ./app/webapp/dist/

RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir ".[prod]"

COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY alembic.ini ./

EXPOSE 8000

CMD ["python", "-m", "app.main"]
