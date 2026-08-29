---
状态: 已接受
日期: 2026-08-29
关联: ADR 0005 / 0007 / docs/system-design.md §4 编排
---

# SQLite 会话持久化与真 interrupt HITL 全模式启用

## 背景

ADR 0005 时代 SQLite（默认配置）无 checkpointer：无会话恢复，HITL 走"软降级"（图不暂停）。`langgraph-checkpoint-sqlite` 依赖早已声明却零 import（首版检查报告 P1-E）。

## 决策

1. `graph/checkpointer.py` 在启动时（`ensure_checkpointer_setup`）用 `aiosqlite` 连接直接构造 `AsyncSqliteSaver` 并 `setup()` 建表；`get_checkpointer()` 返回进程级单例。PostgreSQL 分支行为不变。
2. chat 流式端点：有 checkpointer 时**不再从 DB 前置历史消息**（checkpoint 已含会话历史，避免 `add_messages` 重复注入）。
3. interrupt 真挂起分支补齐落库：写用户消息、`hitl_reviews` 审核行、`qc_hits(severity=hitl)` 与审计——保证工作台复核队列不缺记录。
4. 恢复走真 `Command(resume=...)`：医生修正文本经 hitl 节点回到 draft，responder 补齐免责声明。

## 备选方案

- 维持软降级并文档化：最低成本，但"真 HITL/时间旅行"只剩 Postgres 部署可演示，与面试叙事目标冲突。
- `from_conn_string()` 上下文管理器形态：放弃，一次性消费后无法复用为进程级单例。

## 后果

- 默认开发模式（SQLite）即具备会话持久化与真 interrupt；mock 全链路零外部依赖的性质不变。
- checkpoint 序列化包含 `ScopeResult` 等自定义类型，LangGraph 会告警"unregistered type"（当前仅警告）；升级到 strict msgpack 时需注册 serde。
- 测试隔离靠 `tests/conftest.py` autouse fixture 重置 checkpointer 单例。
