# Care-LifeLine

基于 **LangGraph** 的企业级医疗智能体平台：多 Agent 分级诊疗 + 质控 Agent（规则 + LLM 双层把关）+ 数据闭环 + 主动触发。

> ⚠️ 本系统用于辅助学习与工程演示，**不提供医疗建议，不替代专业医疗判断**。所有输出附带免责声明与可追溯引用。

## 亮点

- **多 Agent 分级诊疗**：Router → Triage / Report / Medication → QC → Responder，全链路可观测、可回放
- **质控 Agent（灵魂）**：确定性规则引擎（可单测、可版本化）+ LLM 语义评审，安全 = 工程能力
- **双模式 LLM**：`LLM_MODE=mock` 零外部依赖可跑；`real` 走 OpenAI 兼容协议（火山方舟 Doubao / DeepSeek），仅改 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` 三项即可切换
- **RAG 指南检索**：混合检索（向量 + BM25，RRF 融合），默认零依赖内存库；配置 `QDRANT_URL` 后启用 Qdrant 向量库
- **持久化与会话恢复**：PostgreSQL + LangGraph PostgresSaver（checkpointer）实现跨请求会话恢复；SQLite 兜底零依赖
- **HITL 医生工作台 + 管理后台**：待审队列、编辑/采纳/驳回、审计、规则开关、运营指标
- **主动触发**：后台定时扫描患者指标、生成复诊提醒（含文件分布式锁，防多实例重复跑）
- **评测体系**：拒答率 / 安全率 / 转人工率 / 合规率 / faithfulness / P95 多维指标，含明确基线与 `make eval` 报告
- **数据闭环**：人工反馈 / HITL 决议 / 评测用例沉淀，系统越用越安全

## 快速开始

```bash
make install       # uv sync
make dev           # 本地 API（http://localhost:8000），默认 mock 模式零外部依赖
make test          # 单元测试（含质量门禁）
make eval          # 评测运行，产出 eval_report.md
```

打开浏览器访问 `http://localhost:8000/` 即为内置前端（对话 / 报告解读 / 慢病管理 / 用药相互作用 / 医生工作台 / 管理后台）。
演示账号：`demo / demo123`（JWT 鉴权）。

### 切换真实模型（Doubao / DeepSeek）

```bash
cp .env.example .env
# 编辑 .env：
LLM_MODE=real
LLM_API_KEY=sk-......          # 你的真实 Key（占位示例 sk-......）
# 默认火山方舟 Doubao；改用 DeepSeek 取消注释 LLM_BASE_URL / LLM_MODEL 两行
make dev
```

### 启用 Qdrant 指南检索

```bash
# .env 中设置：
QDRANT_URL=http://localhost:6333
# 如需本地真实向量化（sentence-transformers）再加：RAG_ENABLED=true
```

### 生产部署

```bash
cp .env.example .env   # 必改 JWT_SECRET
make compose-up       # Postgres + Qdrant + API 一键起（自动构建前端并灌演示数据）
```

前端为 `web/` 下的 React SPA（Arco Design），由 API 同源托管（构建产物 `web/dist`）。

## P2 能力（已实现占位 / 离线基线）

- **用药相互作用 MedicationAgent**：内置离线 DDI 知识库（华法林+阿司匹林 等示例子集），生产可接 RxNorm + FDA 实时接口
- **拍药盒识别 PillboxVision**：`POST /v1/ocr/pillbox` 离线占位实现，生产接 OCR / 多模态模型

## 评测指标

| 指标 | MVP 基线 | v1.0 目标 |
|---|---|---|
| 拒答率 refusal_rate | ≥ 90% | ≥ 95% |
| 安全率 safety_rate | ≥ 90% | ≥ 95% |
| faithfulness | ≥ 0.80 | ≥ 0.85 |
| 合规率 compliance | ≥ 95% | ≥ 98% |
| 转人工率 hitl_rate | ≤ 20% | ≤ 10% |

> 指标口径见 `docs/system-design.md` §9；`make eval` 生成最新基线报告。

## License

MIT（草案，待定）。
