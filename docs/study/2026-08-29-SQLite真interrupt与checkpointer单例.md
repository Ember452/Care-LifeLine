# 2026-08-29 SQLite 上真 interrupt：from_conn_string 的上下文管理器陷阱

## 背景与问题

LangGraph 的真 HITL（`interrupt()` + `Command(resume=...)`）此前只在 Postgres 部署可用；默认 SQLite 模式是"软降级"（图不暂停）。依赖 `langgraph-checkpoint-sqlite` 装了却没 import。目标：让默认开发模式也具备会话持久化与真 interrupt。

## 实现要点

1. **API 陷阱**：`AsyncSqliteSaver.from_conn_string()` 返回的是**一次性异步上下文管理器**，`async with` 进去再出来连接就关了——不能像 Postgres 分支那样存成进程级单例复用。解法：启动时 `conn = await aiosqlite.connect(path)` 后**直接构造** `AsyncSqliteSaver(conn)` + `await saver.setup()`，单例持有 saver 和连接两个引用。
2. **重复注入**：有 checkpointer 后 checkpoint 自带会话历史，chat 端点不能再从 DB 前置历史消息，否则 `add_messages` 把同一轮对话注入两遍。分支：有 checkpointer 只传新消息。
3. **interrupt 分支补落库**：图在 hitl 节点暂停时 draft/qc 都还没产出，工作台队列会缺记录——interrupt 分支补写用户消息、`hitl_reviews` 行、`qc_hits(severity=hitl)` 与审计。
4. **测试隔离**：checkpointer 持有指向各用例临时 SQLite 的连接，跨用例残留会串库。`tests/conftest.py` autouse fixture 前后重置单例（`aiosqlite.Connection.stop()` 同步释放线程）。
5. 恢复后 responder 会给医生修正文本**补免责声明**——质控闭环在人工介入后依然生效，这点写进了断言。

## 面试预演

- 追问："HITL 是怎么实现的？" → 三层：`interrupt()` 挂起图执行、载荷只含 reason/risk（不含原文，防 PHI 进 checkpoint）；SSE 端点检测 `__interrupt__` 改发转人工文案并落审核行；工作台审核后 `Command(resume={"corrected_text":...})` 恢复，修正文本经质控/responder 补齐免责后回给用户。
- 追问："checkpoint 里的自定义类型怎么办？" → 坦诚：`ScopeResult` 等会触发 LangGraph 的 unregistered-type 告警（当前仅警告），strict msgpack 启用前需注册 serde；已记入 ADR 0009 后果段。
