# Care-LifeLine

基于 **LangGraph** 的企业级医疗智能体平台：多 Agent 分级诊疗 + 质控 Agent（规则 + LLM 双层把关）+ 数据闭环。

> ⚠️ 本系统用于辅助学习与工程演示，**不提供医疗建议，不替代专业医疗判断**。所有输出附带免责声明与可追溯引用。

## 亮点

- **多 Agent 分级诊疗**：Router → Triage → Specialist → QC → Responder，全链路可观测、可回放
- **质控 Agent（灵魂）**：确定性规则引擎（可单测、可版本化）+ LLM 语义评审，安全 = 工程能力
- **持久化**：LangGraph Checkpointer（PostgreSQL），会话恢复 + HITL 时间旅行
- **评测体系**：拒答率 / 误放行率 / faithfulness / compliance 多维指标，含明确基线
- **数据闭环**：人工反馈 → 评测用例与质控规则沉淀，系统越用越安全

## 快速开始

```bash
make install       # uv sync
make compose-up    # 起依赖（postgres + qdrant）
make dev           # 本地 API（http://localhost:8000/docs）
make test          # 单元测试
```

详细命令与规范见 [AGENTS.md](./AGENTS.md)，设计依据见 [docs/system-design.md](./docs/system-design.md)。

## 评测指标

| 指标 | MVP 基线 | v1.0 目标 |
|---|---|---|
| 拒答率 | ≥ 90% | ≥ 95% |
| 误放行率 | ≤ 10% | ≤ 5% |
| faithfulness | ≥ 0.80 | ≥ 0.85 |
| 转人工率 | ≤ 20% | ≤ 10% |

> 指标徽章位：CI 评测回归后将在此展示最新结果。

## License

MIT（草案，待定）。
