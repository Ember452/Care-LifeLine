#!/usr/bin/env bash
# 本地一键灌入演示数据（演示用户 + 必要库表）。生产请用 docker compose 中的等价步骤。
set -euo pipefail

uv run python -m care_lifeline.db.seed_demo
