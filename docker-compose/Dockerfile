FROM python:3.12-slim-bookworm AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/python/.venv/bin:$PATH"

COPY python/pyproject.toml python/uv.lock python/.python-version /app/python/
RUN uv sync --frozen --no-dev --no-install-project --directory python

COPY config ./config
COPY web ./web

CMD ["sh", "-c", "gunicorn web.wsgi:app --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-2} --timeout ${GUNICORN_TIMEOUT:-120}"]

FROM nginx:1.27-alpine AS nginx
COPY docker-compose/nginx.conf /etc/nginx/conf.d/default.conf
