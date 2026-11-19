FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY backend/ ./backend/
COPY examples/ ./examples/
COPY --chown=nobody:nogroup forecast/result.json ./forecast/result.json
COPY --from=web /web/dist ./frontend/dist
USER nobody
EXPOSE 8000
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
