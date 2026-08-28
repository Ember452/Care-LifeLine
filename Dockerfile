FROM node:20-bookworm-slim AS web
WORKDIR /web
RUN npm install -g pnpm
COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY web ./web
RUN pnpm build

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* README.md ./
COPY src ./src
COPY --from=web /web/dist ./web/dist

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "care_lifeline.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
