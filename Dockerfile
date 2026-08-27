FROM python:3.13-slim

WORKDIR /app

# uv 官方镜像安装
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 先拷贝依赖清单，利用层缓存（uv.lock 生成后自动生效）
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen

COPY src ./src

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "care_lifeline.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
