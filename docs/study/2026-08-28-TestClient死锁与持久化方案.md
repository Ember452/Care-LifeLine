# TestClient 下 LangGraph checkpointer 与异步 SQLAlchemy 死锁

> 日期：2026-08-28 ｜ 关联功能 / 任务：M2-4 会话持久化

## 背景与问题

M2 要把对话持久化并跨请求恢复，默认用 SQLite、零外部依赖跑通且可被 pytest 覆盖。但挂上 LangGraph `PostgresSaver`/`SqliteSaver` checkpointer 或 `aiosqlite` 异步 SQLAlchemy 后，`fastapi.testclient.TestClient` 一发请求就**永久挂起**（CI 必挂）。最小复现：一个不含 DB、不含 checkpointer 的 `graph.ainvoke` 流式端点完全正常；只要加 checkpointer 或 aiosqlite，TestClient 即死锁。

## 实现要点

- 根因：TestClient 用 anyio **阻塞 portal** 把 ASGI app 跑在独立线程+事件循环里；LangGraph 的 checkpoint 读写与 `aiosqlite` 的异步 IO 都和这个 portal 的事件循环相互阻塞，形成死锁（即便 `MemorySaver` 也死锁，说明是 checkpointer 机制本身而非 DB 驱动）。
- 决策：放弃 LangGraph checkpointer 做长程记忆；改为**同步 SQLAlchemy 2.0** + `starlette.concurrency.run_in_threadpool` 在异步端点里调用，恢复由自研 `session_store` 拼 `state["messages"]` 完成；`graph.compile()` 不加 checkpointer。Postgres 仍经 `CARE_DATABASE_URL` 启用。
- 关键技巧：用「最小端点 + 逐步加依赖」二分定位死锁源；`run_in_threadpool` 把同步 DB 隔离出事件循环。实测：58 测试全绿，默认 SQLite 零依赖可跑。

## 面试预演

- Q：为什么不用 LangGraph 官方 PostgresSaver 做记忆？→ A：它在 TestClient/同步测试 harness 下与 anyio portal 死锁，MVP 要可测可零依赖跑；自研 session_store 显式拼 messages 更可控、易测，代价是放弃时间旅行能力。
- Q：同步 DB 会不会拖慢异步接口？→ A：走 `run_in_threadpool` 进线程池，不阻塞事件循环；MVP 吞吐下无感知，且 SQLite/postgres 驱动都比纯内存推理慢得多，瓶颈在 LLM 不在 DB。
- Q：流式响应里改请求体脱敏怎么不掉流式？→ A：PHI 中间件逐 `http.request` 块惰性 `mask()` 透传，不缓冲整段 body，保留 `more_body` 语义（见 ADR 0006）。
