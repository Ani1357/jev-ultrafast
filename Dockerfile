# Price Check NL: the web page (default) or CLI, with its own Chromium inside the container.
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium xvfb xauth fonts-liberation curl ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.8.17

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY jev_ultrafast ./jev_ultrafast
COPY pricecheck ./pricecheck
RUN uv sync --frozen --no-dev
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
USER app
# Reports land in /data/artifacts; Chrome's profile in /data/chrome.
WORKDIR /data
ENV PATH=/app/.venv/bin:$PATH \
    BU_CDP_URL=http://127.0.0.1:9222 \
    BH_UPDATE_CHECK=0 \
    BH_TELEMETRY=0 \
    PRICECHECK_BIND=0.0.0.0 \
    PRICECHECK_ALLOWED_HOSTS=localhost:8767,127.0.0.1:8767 \
    CHROME_HEADLESS=0
EXPOSE 8767
ENTRYPOINT ["tini", "--", "entrypoint.sh"]
CMD ["pricecheck-web"]
