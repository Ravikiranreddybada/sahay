# API + MCP servers image (same code; command selects the role)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY sahay ./sahay
COPY data ./data
COPY evals ./evals
RUN pip install ".[prod]" && useradd -u 10001 -m app && mkdir -p /app/var && chown -R app /app
USER app
EXPOSE 8000
ENV PORT=8000 WEB_CONCURRENCY=2
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'))"
# PORT comes from the host (Render); WEB_CONCURRENCY is read by uvicorn (set 1 on small instances)
CMD ["sh", "-c", "exec uvicorn sahay.main:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 75"]
