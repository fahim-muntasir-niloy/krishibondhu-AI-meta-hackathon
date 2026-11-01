# The whole app: FastAPI serving the API and the built frontend (main.py).
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# Pillow's bundled raqm loads fribidi at runtime; without it Bangla labels on
# annotated photos render unshaped.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libfribidi0 libharfbuzz0b \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 2024
# Apply the Postgres schema first (idempotent, a second or two), then serve.
CMD ["sh", "-c", "krishi-db migrate && exec python main.py"]
