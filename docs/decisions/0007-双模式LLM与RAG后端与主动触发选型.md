---
状态: 已接受
日期: 2026-08-28
关联: docs/system-design.md §3 技术栈 / §9 评测
---

# 双模式 LLM、RAG 后端与主动触发选型

## 背景

M1–M5 已基本完成，但计划中的"真实可用"项尚未落地：真实 LLM 仅在 `chat.py` 硬编码了 `MockProvider`，Qdrant、PostgresSaver 时间旅行、主动调度、React 前端均未接通。需在保持 mock 零依赖可跑的前提下，补齐计划要求的能力。

## 决策

1. **LLM 双模式**：统一经 `llm/provider.py:make_provider()` 选择。`real` 模式使用 OpenAI 兼容协议（`langchain_openai.ChatOpenAI`，配置 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`），默认指向火山方舟 Doubao，改三项即可切 DeepSeek。`chat.py`、`reports.py`、`report_interpreter` 节点全部改走 `make_provider()`。
2. **RAG 后端可插拔**：`VectorStore` 抽象下提供 `MemoryVectorStore`（默认零依赖）与 `QdrantVectorStore`；`tools/rag/registry.py` 按 `QDRANT_URL` 选择，按 `RAG_ENABLED` 选择本地 sentence-transformers 或确定性 mock 向量。检索失败优雅降级为静态引用。指南语料独立于评测集（`data/guidelines/*.md`）。
3. **会话恢复**：PostgreSQL 下用 LangGraph `AsyncPostgresSaver`（checkpointer）实现跨请求恢复；SQLite 下无 checkpointer。`chat.py` 在 postgres 时传 `thread_id`。
4. **主动触发**：`proactive/scheduler.py` 后台定时扫描患者指标并缓存提醒，配文件分布式锁（多实例防重复），启动时先跑一次；端点优先返回缓存。
5. **前端**：保留 `src/.../static/index.html` 作为保底 UI；`web/` React SPA 构建产物 `web/dist` 由 API 同源托管（`/` 与 `/assets/*`），通过 catch-all 路由实现 SPA fallback。

## 备选方案

- 真实 LLM 直接写死某厂商 SDK：放弃，违反"可切换"原则。
- Qdrant 强制启用：放弃，会破坏零依赖 mock 演示。
- 主动触发用 Redis 锁 / Celery：过度设计，文件锁足够单机，Redis 作为多机扩展点保留。

## 后果

- mock 模式仍是默认且全绿（CI/演示），real/Qdrant/Postgres 通过环境变量激活。
- P2 的 MedicationAgent（离线 DDI 库）、PillboxVision（OCR 占位）已落地可测，生产接真实 API 即可。
- 风险：real 模式依赖外部网络与 Key；Qdrant 不可达时自动降级。
