# M3 设计文档：报告解读 + 慢病管理

> 日期：2026-08-28 ｜ 阶段：M2 之后 ｜ 来源 spec：`docs/development-plan.md` §M3
> 关联：ADR 0005（持久化恢复）、ADR 0006（PHI 中间件）

## 1. 目标

在 M2 的"可信赖底座"（质控/持久化/鉴权/HITL）之上，补齐**临床价值闭环**的两个核心能力：

1. **报告解读**：粘贴化验/检查报告 → 结构化字段抽取 + 异常标注 + 指南引用。
2. **慢病管理**：患者纵向指标记忆 + 趋势展示 + Proactive 主动提醒。

M3 后端：`tools/rag`（RAG 管线）、`graph/nodes/report_interpreter`（结构化解读）、`memory/`（患者记忆）、`proactive/`（主动触发）。前端：`web/` 报告页 + 慢病面板（本期先以最小可用页面验证，完整设计系统留 M5）。

## 2. 已有（M2 交付）

- `config`、`llm/`、`graph/(state,builder,nodes)`、`api/(app,routers/*)`、`db/*`、`safety/*`、`api/security.py`。
- 会话持久化（`session_store`）+ JWT 鉴权 + PHI 脱敏中间件。
- qc_rules 覆盖率 100%；58 单测/评测全绿。

## 3. 目录结构（新增/改动）

```
src/care_lifeline/
  tools/
    rag/
      chunker.py        # M3-1 中文语义分块
      embeddings.py     # M3-1 EmbeddingPort（Mock/Local）
      retriever.py      # M3-1 HybridRetriever（BM25+向量，内存/Qdrant）
      reranker.py       # M3-1 Reranker（Mock/CrossEncoder）
      index_builder.py  # M3-1 建库脚本（make index）
      store.py          # M3-1 内存向量库（测试/零依赖兜底）
  graph/nodes/
    report_interpreter.py  # M3-2 结构化解读节点
  memory/
    patient_memory.py      # M3-3 患者纵向指标存储（复用 db）
  proactive/
    trigger.py             # M3-4 最小触发（事件/定时 + 分布式锁）
  eval/
    datasets/              # 报告样本、红队/拒答集（防泄漏，不进 RAG 语料）
```

## 4. 设计细节

### 4.1 RAG 管线（M3-1）— 零依赖可测优先

- **分块** `chunk_text(text) -> list[Chunk]`：按标题（`#`/数字序号）与空行切段，段内再按 ≤500 字断句；保留 `source`/`section` 元数据。
- **EmbeddingPort**：`embed(texts: list[str]) -> list[list[float]]`。`MockEmbedding`（基于哈希的确定性向量，测试用，不下载模型）；`LocalEmbedding`（sentence-transformers MiniLM，仅 `RAG_ENABLED=1` 时启用）。
- **HybridRetriever**：`retrieve(query, k) -> list[Chunk]`。BM25（`rank_bm25`，本地语料）与向量（`store.py` 内存库或 Qdrant）融合（RRF 倒数排名融合）。`store.py` 提供内存向量库，确保无 Qdrant 也能跑通测试。
- **Reranker**：`rerank(query, chunks) -> list[Chunk]`。`MockReranker`（保序）/`CrossEncoderReranker`（MiniLM）。
- **index_builder**：扫描 `data/guidelines/` → 分块 → 嵌入 → 写入向量库 + BM25 语料；`make index` 触发。

### 4.2 报告解读（M3-2）

- `report_interpreter_node(state)`：接收用户报告文本 → 调 RAG 召回指南 → LLM（mock 模式下确定性模板）抽取结构化字段 `{项目, 结果, 参考范围, 异常}` → 标注异常（超出参考范围）→ 每个异常带指南引用。
- 输出进入 `state["report"]`，并在 `responder` 后随 SSE `citation` 事件下发；受 `qc_node` 双层把关（引用必须 grounded）。

### 4.3 患者记忆（M3-3）

- 复用 `db`：新增 `PatientMetric`（指标时序）表；`patient_memory` 提供 `append_metric` / `get_trend`。会话级记忆已通过 `session_store` 实现，本期补"跨会话"患者级纵向记忆。

### 4.4 Proactive 最小触发（M3-4）

- `trigger.py`：`check(patient)` 基于指标趋势（如血压连续超标）产出提醒；定时任务用 `asyncio` 循环 + 进程级分布式锁（文件锁/`redis` 可选）防重复。M3 仅做最小事件触发 + 锁骨架，深度事件驱动留 P2。

### 4.5 / 4.6 前端（M3-5/6）

- 报告页：粘贴文本 → 展示结构化解读 + 异常标注 + 引用。慢病面板：趋势图（canvas/SVG，零图表库依赖）+ 提醒列表。完整设计系统留 M5。

## 5. 接口衔接

- 新增 `POST /v1/report/interpret`（鉴权）接收报告文本，返回结构化解读 + 引用；复用 SSE/`citation` 契约。
- `graph` 新增 `report_interpreter` 节点（已在 M1 builder 中占位），M3 落地实现。
- 所有外部调用（嵌入/检索/Rerank）经协议抽象，测试用 Mock，避免 CI 下载模型。

## 6. 测试策略

- `tests/unit/rag/`：分块边界、MockEmbedding 确定性、HybridRetriever 融合召回、MockReranker 保序。
- `tests/unit/test_report_interpreter.py`：mock 模式结构化抽取 + 异常标注 + 引用 grounding。
- `tests/unit/test_patient_memory.py`：指标写入/趋势读取。
- `tests/eval/`：端到端"粘贴报告→解读→引用"走通（默认 mock）。
- 门禁：RAG/解读模块单测覆盖核心分支；`make check` 全绿。

## 7. 风险

- 模型下载占用 CI：默认 `RAG_ENABLED=0`，仅 Mock 链路跑测试；真实嵌入留 `make index` 本地触发。
- 幻觉/越界：报告解读结论必须带指南引用，过 `qc_node` groundedness 校验。
- 隐私：报告文本属 PHI，入口中间件已脱敏；患者指标存库遵循同套 PHI/审计约束。

## 8. 交付状态（2026-08-28）

- M3-1 RAG 管线：`tools/rag/*`（分块/嵌入/内存向量库/混合检索 RRF/重排/建库），零依赖 Mock 链路，11 单测。
- M3-2 报告解读：`tools/report_interpreter.py`（Mock 确定性 + LLM 带兜底）、`graph/nodes/report_interpreter.py`、`POST /v1/report/interpret`。
- M3-3 患者记忆：`db/models.PatientMetric` + 迁移、`memory/patient_memory.py`（append/trend/latest）。
- M3-4 Proactive：`proactive/trigger.py` 阈值提醒 + `GET /v1/patients/{id}/reminders`、`POST /v1/patients/{id}/metrics`。
- M3-5/6 前端：`api/static/index.html` 增加报告解读 + 慢病管理面板（复用现有静态页，未搭 React SPA，留 M5）。
- 门禁：`make check` 全绿（82 passed，ruff/mypy 干净）。
