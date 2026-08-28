# Care-LifeLine

基于 **LangGraph** 的企业级医疗智能体平台：多 Agent 分级诊疗 + 质控 Agent（规则 + LLM 双层把关）+ 数据闭环。

> ⚠️ 本系统用于辅助学习与工程演示，**不提供医疗建议，不替代专业医疗判断**。所有输出附带免责声明与可追溯引用。

## 亮点

- **多 Agent 分级诊疗**：Router → Triage → Specialist → QC → Responder，全链路可观测、可回放
- **质控 Agent（灵魂）**：确定性规则引擎（可单测、可版本化）+ LLM 语义评审，安全 = 工程能力
- **持久化**：同步 SQLAlchemy（SQLite 默认兜底 / PostgreSQL 可选），会话、审计、HITL 审阅、患者指标统一落库
- **评测体系**：拒答率 / 安全率 / 转人工率 / 合规率 / faithfulness / P95 多维指标，含明确基线与 `make eval` 报告
- **数据闭环**：人工反馈 → 评测用例与质控规则沉淀，系统越用越安全

## 快速开始

```bash
make install       # uv sync
make dev           # 本地 API（http://localhost:8000），默认 mock 模式零外部依赖
make test          # 单元测试（含质量门禁）
make eval          # 评测运行，产出 eval_report.md
```

打开浏览器访问 `http://localhost:8000/` 即为内置前端（对话 / 报告解读 / 慢病管理 / 医生工作台 / 管理后台）。
演示账号：`demo / demo123`（JWT 鉴权）。

生产部署：

```bash
cp .env.example .env   # 必改 JWT_SECRET
make compose-up       # Postgres + API 一键起（自动灌演示数据）
```

详细命令与规范见 [AGENTS.md](./AGENTS.md)，设计依据见 [docs/system-design.md](./docs/system-design.md)。

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
