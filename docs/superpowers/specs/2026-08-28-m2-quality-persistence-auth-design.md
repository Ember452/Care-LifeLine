# M2 设计文档：质控 + 持久化 + 鉴权

> 日期：2026-08-28 ｜ 阶段：M1 之后 ｜ 来源 spec：`docs/system-design.md` v0.2 + `docs/development-plan.md` §2/M2
> 本文件为 superpowers `brainstorming` 架构路径产出的设计文档，评审通过后将由 `writing-plans` 拆为实现计划。

## 1. 目标与出口验证

在 M1 的 mock 流式问诊之上补齐"可信赖医疗 Agent"底座：

- **双层质控**：规则引擎 v1（纯函数，`tests/unit/qc_rules` 覆盖率 100% 门禁）+ LLM 语义评审层
- **PHI 入口脱敏**：FastAPI 中间件，请求体先脱敏再进路由，日志只记脱敏后文本
- **持久化**：PostgresSaver 挂接 + 会话/审计追加写，支持断线恢复
- **鉴权**：JWT + 角色权限（doctor / patient / admin）
- **HITL**：high-risk 会话 interrupt 挂起，医生 review 后 `update_state` 恢复

出口：登录 → 问诊（mock）→ 会话断线后从列表恢复继续对话；`qc_rules` 单测覆盖率 100%。

## 2. 依赖方向与目录

依赖方向（单向，沿用 AGENTS.md）：`api → graph → 能力层(tools/memory)`；`safety/audit` 横切被上层调用，禁止反向。

已有（M1）：`config`、`llm/`、`graph/(state,builder,nodes)`、`api/(app,routers/chat)`、前端契约/请求层/SSE/chat 页。

新增/改动：

```
src/care_lifeline/
  safety/rules_engine.py        # M2-1 规则引擎 v1（纯函数）
  safety/phi.py                 # M2-2 PHI 脱敏（正则 + 简单 NER）
  api/middleware/phi.py         # M2-2 脱敏中间件
  db/engine.py                  # M2-4 psycopg async engine
  db/models.py                  # M2-4 SQLAlchemy 2.0 async ORM
  db/migrations/001_init.sql    # M2-4 建表脚本
  api/auth.py                   # M2-5 登录/JWT/依赖注入
  api/routers/sessions.py       # M2-4 + M2-7 会话 CRUD
  graph/nodes/qc.py             # M2-3 替换为规则+LLM 双层
  graph/nodes/hitl.py           # M2-6 中断/恢复
  api/routers/chat.py           # M2-3/4/5/6 接入鉴权+持久化+PHI
web/src/pages/LoginPage.tsx     # M2-7 登录页
web/src/stores/session.ts       # M2-5/7 增强（token/user/角色）
web/src/pages/ChatPage.tsx      # M2-7 会话管理接入
```

## 3. 关键设计

### 3.1 质控规则引擎 v1（M2-1，`safety/rules_engine.py`）

- 纯函数、无 IO、无 LLM，可单测、可确定。
- 数据结构：
  - `Rule` dataclass：`code / description / severity / evaluate(draft, ctx) -> Violation | None`
  - `Violation`：`code / severity / message`
  - `load_ruleset(version: int = 1) -> list[Rule]`
  - `evaluate_all(rules, draft, ctx) -> list[Violation]`（聚合；`severity=blocking` 命中后短路）
- `ctx` 至少含：`risk_level`（来自 router）、`has_disclaimer`、`has_citation`。
- 内置规则（v1 起步集）：
  - 越界请求拒答：`开处方/开药/诊断结论` 类词 → `blocking`（拒答）
  - 紧急词：`胸痛/呼吸困难/卒中征兆` → `blocking` + 标记转人工
  - 缺免责声明 → `warning`
  - 缺引用 → `warning`
  - 正常输出 → 通过
- 覆盖率 100%：`tests/unit/qc_rules/test_rules_engine.py` ≥ 12 条，逐规则 + 聚合 + 短路；在 `pyproject.toml` 对 `src/care_lifeline/safety` 单独设 `fail_under = 100`（或单独 `pytest-cov` 命令门禁），避免拖累整体 80%。

### 3.2 PHI 脱敏（M2-2）

- `safety/phi.py`：`mask(text) -> str`；正则覆盖姓名/身份证号/手机号/病历号 → `[PHI]`；幂等（二次脱敏不变）。
- `api/middleware/phi.py`：FastAPI middleware，读取请求体 → 脱敏 → 注入修改后的 `request` 再进路由；响应与日志统一只记录脱敏后文本。
- 测试：`tests/unit/test_phi.py` 覆盖各类 PI 替换、普通文本不变、幂等。

### 3.3 LLM 语义评审层（M2-3，替换 M1 的 qc 节点占位）

- 新增 `LLMReviewer.check(draft, evidence) -> QCResult{status, risk_score, violations}`。
- 阈值读 `settings.qc_risk_threshold`（默认 0.75）；mock 模式返回确定性分数便于测试。
- `graph/nodes/qc.py` 改为：先跑规则引擎（3.1），再跑 `LLMReviewer`，合并 `QCResult`：
  - 规则 `blocking` → 直接 `refused`/`hitl`（短路）
  - 否则 LLM 风险分 > 阈值 → `hitl`，否则 `passed`
- 测试：`tests/unit/qc_rules/test_llm_reviewer.py` 覆盖高/低风险分支。

### 3.4 持久化（M2-4）

- `db/engine.py`：psycopg async engine + `async_sessionmaker`。
- `db/models.py`：SQLAlchemy 2.0 async ORM，按 `development-plan.md` §3.1 建表（users / patients / sessions / messages / citations / qc_rules / qc_hits / audit_logs；feedback / eval_* 按需，M4 再扩）。
- `db/migrations/001_init.sql`：建表脚本；`make compose-up` 起 postgres 后执行（或 engine 内 `create_all` 用于本地/dev）。
- `graph/builder.py`：挂 `PostgresSaver`（需 `checkpointer` + `await graph.ainvoke`，M1 用的是同步 `invoke`，M2 改为 async 路径或保留同步 + MemorySaver 兜底）。
- 同一 `thread_id`（= `sessions.thread_id`）第二次调用可恢复上下文；`audit_logs` 在端点/节点处追加写入轨迹。
- 测试：`tests/eval/test_persistence.py` 用 SQLite（`sqlite+aiosqlite`）验证恢复 + 审计可见。

### 3.5 JWT 鉴权（M2-5）

- `api/auth.py`：`python-jose` 签发/校验 JWT；`passlib.bcrypt` 校验密码；`/v1/auth/login` 返回 `{token, user}`；`get_current_user` 依赖注入；路由级角色权限（doctor 才能访问 workbench，M4 落地）。
- 种子数据：admin / doctor / patient 三个演示账号（bcrypt 哈希）。
- 测试：`tests/eval/test_auth.py` 覆盖登录返 token、无 token → 401、角色越权 → 403。

### 3.6 HITL 中断/恢复（M2-6）

- `graph/builder.py`：high-risk（规则/LLM 判定）节点后 `interrupt()` 挂起；生成 workbench 待复核项（写入 `feedback`/`qc_hits`）。
- 医生 `review(approve|reject|edit)` 后 `graph.update_state` 恢复执行并产出最终结果。
- 测试：`tests/eval/test_hitl.py` 覆盖 pending → approve 后继续输出。

### 3.7 前端：登录 + 会话管理（M2-7）

- `LoginPage`：账号密码表单（演示账号提示），成功存 token+user 跳首页；401 全局跳登录（复用 M0-4 的 `http.ts`/`session.ts`）。
- 会话管理：首页/侧栏列出历史会话（来自 `/v1/sessions`），新建、点击恢复（`thread_id` 传入 ChatPage）；登录态持久化 localStorage。
- 复用 M1 的 chat 页流式能力，仅补齐会话生命周期。

## 4. 与 M1 的接口衔接

- M1 `qc` 节点占位 → M2-3 替换为规则+LLM 双层（接口仍是返回 `qc_result`）。
- M1 `chat` 端点 → M2 加 PHI 中间件 + 鉴权依赖 + 持久化（签名不变，仍返回 SSE）。
- 前端 chat 页流式渲染不变；M2-7 仅增加登录与会话持久。

## 5. 测试策略与质量门禁

- 单元：`qc_rules` 100% 门禁（独立 `pytest-cov` 命令或 `fail_under=100` 针对 safety 模块）；`phi`、`llm_reviewer` 单测。
- 集成：`auth` / `persistence` / `hitl` 用 SQLite（`aiosqlite`）兜底，不依赖 Docker。
- 前端：`LoginPage` + 会话管理联调（mock 模式）。
- 全程 `ruff` / `mypy` / `make check` 绿；前端 `tsc -b` + `vitest` 绿。

## 6. 风险与回避

- **Postgres 依赖**：生产/运行时用 Postgres（`make compose-up` 起依赖）。**集成测试统一用 SQLite 异步兜底（`aiosqlite`），不依赖 Docker**，保证 `make check` 在任何环境可跑；`engine.py` 按 `settings.database_url` 选择驱动（测试传 `sqlite+aiosqlite:///...`）。ORM 模型用跨库兼容写法（避免 PG 专有类型）。
- **同步/异步**：M1 图用同步 `invoke`；M2 持久化需 async。统一切到 async 路径（`ainvoke` + `AsyncPostgresSaver`），M1 的同步调用点同步适配，避免混用。
- **覆盖率门禁**：qc_rules 单独 100%，不拉高整体阈值（整体维持 80），防止误伤。

## 7. 后续

本文档评审通过后，调用 `writing-plans` 将 M2-1~M2-7 拆为带校验点的实现计划，再按 TDD 逐任务开发。
