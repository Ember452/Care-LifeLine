# 统一命令入口：本地与 CI 使用同一套命令（Makefile 与 .github/workflows 保持同步）
PYTHON ?= uv run

.PHONY: install dev test eval eval-real calibrate lint type check web-install web-test web-build web-check compose-up compose-down clean

install:          ## 安装依赖（uv sync）
	uv sync

dev:              ## 本地启动 API（--reload）
	$(PYTHON) uvicorn care_lifeline.api.app:app --reload --port 8000

test:             ## 单元测试
	$(PYTHON) pytest tests/unit -q --cov=care_lifeline --cov-report=term-missing

eval:             ## 评测运行（mock 模式，输出 eval_report.md）
	$(PYTHON) python -m care_lifeline.eval.suite --mode mock

eval-real:        ## 评测运行（real 模式，输出 eval_report_real.md；需 CARE_LLM_API_KEY）
	$(PYTHON) python -m care_lifeline.eval.suite --mode real

calibrate:        ## QC 阈值校准（real 模式：标注集 + PR 曲线选点，输出 eval_calibration.md）
	$(PYTHON) python -m care_lifeline.eval.calibrate --mode real

lint:             ## Lint 检查
	$(PYTHON) ruff check src tests

type:             ## 类型检查
	$(PYTHON) mypy src

check: lint type test   ## 质量门禁（后端，CI 同款）

web-install:      ## 安装前端依赖（pnpm）
	cd web && pnpm install

web-test:         ## 前端类型检查 + 单测（tsc + vitest）
	cd web && pnpm run typecheck && pnpm run test

web-build:        ## 构建前端产物（web/dist）
	cd web && pnpm run build

web-check: web-install web-test web-build   ## 前端质量门禁（CI 同款）

compose-up:       ## 起本地依赖（postgres + qdrant + api）
	docker compose up -d --build

compose-down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml
