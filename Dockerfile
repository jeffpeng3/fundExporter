FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
RUN groupadd -r fundexporter && useradd -r -g fundexporter fundexporter
COPY --from=builder /app/.venv /app/.venv
WORKDIR /app
COPY fund_exporter.py fund_parser.py gist_store.py nav_fetcher.py index.html ./
USER fundexporter
ENV PATH="/app/.venv/bin:$PATH"
ENV EXPORTER_PORT=8000
EXPOSE 8000
CMD ["python", "fund_exporter.py"]
