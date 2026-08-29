状态: 已接受
日期: 2026-08-29
关联: docs/system-design.md §10 可观测性；ADR-0007、ADR-0011

# 运行时可观测性：进程内指标注册表与 token 计量

## 背景

设计文档 §10 把 tracing/成本核算写成差异化卖点，但代码里只有
`record_latency_ms` 一个端到端 P95 采样：没有每节点延迟、没有 token 用量、
没有质控结论计数。管理后台的"可观测性"有名无实。

## 决策

1. **自建进程内指标注册表**（`api/runtime.py` 扩展），不引入 Langfuse/
   Prometheus：与既有 `record_latency_ms` 同风格——热路径只做有界内存
   追加（1000 样本 / 200 会话），零网络与 DB 开销，重启清零可接受。
   三类新指标：每节点延迟（count/p50/p95）、质控结论计数
   （passed/warning/hitl/refused）、token 用量（全局累计 + 会话累计）。
2. **节点计时走状态增量**：builder 用 `_timed` 包装器包住全部 11 个节点
   （async/sync 分工厂实现，保留 medication 的 coroutine 语义），把毫秒
   耗时写进状态增量的 `perf_node_ms`；chat.py 从 astream updates 消费后
   记入注册表。不在图外做侵入式埋点，保持依赖方向（api 消费 graph 产出）。
3. **token 计量双口径**：`TokenUsage`（input/output/estimated）。real 模式
   优先读响应自带的 `usage_metadata`（真实计量）；mock 模式与真实 usage
   缺失时按字符启发式估算（~2 字符/token）并**显式标记 estimated**——
   估算值可让计量管线在 CI 全程回归，但绝不与真实计量混淆。
   `LLMProvider` 协议增加 `last_usage` 约定，chat.py 每请求结束后采集。
4. **消费出口**：SSE `done` 事件附带 `token_usage`（前端契约向后兼容）；
   `/v1/admin/metrics` 新增 `node_latency` / `qc_status_counts` /
   `token_usage` 三块。

## 备选方案

- Langfuse/OTel：能力更强但需要外部服务与上报链路，演示环境不可控；
  保留为演进项——注册表的采集点（节点计时、provider 用量）就是将来
  接 Langfuse 的埋点位置。
- 把节点计时写进 LangGraph config 或 callback：与 LangGraph 内部机制耦合
  较深，状态增量方案更直白且对 astream 消费方天然可见。

## 后果

- `/admin/metrics` 拿到真实的每节点 P50/P95 与每会话 token 累计，
  "每会话成本"有了数据源（token 数；接定价表即成本）。
- mock 模式下 token 数字是估算值，仅用于管线演示与回归（字段级标注）。
- `perf_node_ms` 随状态进入 checkpoint（一个浮点数，开销可忽略）。
