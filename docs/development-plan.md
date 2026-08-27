# Care-LifeLine 全栈开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按本计划开发完成后，交付一个**可上线形态的完整全栈项目**——后端多 Agent 医疗平台 + 前端飞书级体验的 React 应用，Docker Compose 一键跑通，支持真实 LLM / Mock 双模式，含评测、审计、HITL 工作台与管理后台。

**Architecture:** 后端 FastAPI + LangGraph（Supervisor 多 Agent + Checkpointer）分层（api → graph → 能力层，safety/audit 横切），PostgreSQL 存会话/审计/反馈/规则/评测，Qdrant 存指南向量；前端为独立 React SPA（`web/`），REST + SSE 流式与后端通信，飞书式布局与设计系统；两者通过 docker compose 编排。前端与后端在每个里程碑内**同步并行开发**，契约先行（§3 定义全部跨端接口）。

**Tech Stack:**
- 后端：Python 3.13 + uv + FastAPI + LangGraph/LangChain + psycopg + Qdrant + pydantic-settings
- 前端：React 18 + TypeScript + Vite + Arco Design（字节系组件库）+ React Router + Zustand + TanStack Query + Recharts + react-markdown
- 基础设施：Docker Compose（web/api/postgres/qdrant）+ GitHub Actions（ci/eval）+ ruff/mypy/pytest/pre-commit

**Spec:** `docs/system-design.md`（v0.2，单一事实来源）+ `docs/decisions/0001-0004`（ADR）。本计划从 spec 论证而来，执行者需同时阅读 spec 与 ADR。

## 全局约束（每个任务都隐含遵守）

1. Python 3.13 + uv（唯一包管理）；前端 Node ≥ 22 + pnpm 或 npm（推荐 pnpm）。
2. 依赖方向单向：`api → graph → tools/memory`；`safety/audit` 横切被上层调用；前端页面 → services → 后端，禁止反向。
3. 代码拆分标准见 `AGENTS.md`（单一职责 / 圈复杂度>10 / 参数>5 / 抽象混杂 / 依赖>8 / 测试失衡 → 拆，与文件长度无关）。
4. TDD：先写失败测试 → 确认失败 → 最小实现 → 通过 → commit。质控规则单测覆盖率 100% 门禁。
5. Commit 规范：**不主动 commit**，须用户同意；信息用中文 `type: 摘要`；批次逻辑内聚。
6. 行为变更先更新 `docs/system-design.md`（版本号 +1）；重大决策必须新增 `docs/decisions/NNNN-*.md`。
7. 安全红线：不输出诊断/处方；高风险强制 HITL；输出带引用+免责；PHI 入口脱敏；密钥只走环境变量。
8. 前端设计遵循 §6 设计规范（不 AI 味）。

## 0. 里程碑总览（约 10 周，前后端同步）

| 里程碑 | 周期 | 后端 | 前端 | 出口验证 |
|---|---|---|---|---|
| M0 工程骨架 | 1 周 | uv/src/config/CI | Vite+Arco+布局+请求层 | 双端可跑，CI 绿 |
| M1 最小图+流式 | 1.5 周 | LLM Provider 抽象+最小图+SSE | 对话页（流式） | 无 key 端到端问诊 |
| M2 质控+持久化+鉴权 | 2 周 | 规则引擎/PHI/Checkpointer/JWT/HITL | 登录+会话管理 | 会话恢复，规则 100% |
| M3 报告+慢病 | 2 周 | RAG/报告解读/患者记忆/Proactive | 报告页+慢病面板 | 报告端到端+图表 |
| M4 工作台+管理后台 | 2 周 | 复核队列/反馈沉淀/评测API/审计API | HITL 工作台+管理后台 | 反馈→沉淀链路 |
| M5 评测+部署+打磨 | 1.5 周 | eval 套件/评测回归 | 设计打磨/构建优化 | compose 一键全栈 |
| P2 可选项 | — | 药盒识别/方案C流式QC/语义缓存 | 对应页面 | 按时间 |

## 1. 前端技术栈与目录（定案）

依赖：`react@18` `react-dom@18` `react-router-dom@6` `@arco-design/web-react` `zustand` `@tanstack/react-query@5` `recharts` `dayjs` `react-markdown` `remark-gfm` `ahooks`；dev 依赖：`vitest` `@testing-library/react` `jsdom`

```
web/
  package.json  pnpm-lock.yaml  vite.config.ts  tsconfig.json  index.html
  src/
    main.tsx
    app/router.tsx               # 路由表（懒加载页面）
    layouts/AppLayout.tsx        # 飞书式布局：左侧 220px 导航 + 顶部 52px 栏
    styles/tokens.css            # 设计 tokens（§6）
    services/http.ts             # fetch 封装：JWT 注入、统一错误、AbortSignal
    services/chat.ts             # SSE 流式客户端（fetch + ReadableStream 解析）
    services/api.ts              # 各端点封装（§3.2 契约）
    stores/session.ts            # zustand：token/user/会话列表
    hooks/useChatStream.ts       # 流式消息 hook（累积 token、引用、qc 事件）
    components/                  # Markdown.tsx CitationCard.tsx RiskBadge.tsx StreamMessage.tsx
                                 # EmptyState.tsx Uploader.tsx TrendChart.tsx AuditTimeline.tsx
    pages/                       # LoginPage HomePage ChatPage ReportPage ChronicPage
                                 # WorkbenchPage AdminPage SettingsPage NotFoundPage
    types/contract.ts            # 前后端契约类型（与 §3 对齐）
    utils/
  .env.example                   # VITE_API_BASE（默认 /v1，走 vite proxy）
```

`vite.config.ts` 关键配置：`server.proxy = { '/v1': 'http://localhost:8000' }`，`resolve.alias { '@': '/src' }`。

## 2. 后端目录（沿用 v0.2，补充 api 内部结构）

```
src/care_lifeline/
  config.py                     # pydantic-settings（含 LLM_MODE=mock|real 等）
  api/                          # main.py(入口) auth.py(登录/依赖注入) routers/(chat/report/patient/workbench/admin) middleware/(phi.py)
  graph/                        # builder.py state.py nodes/(router triage report_interpreter medication qc responder hitl)
  llm/                          # provider.py(抽象) real_provider.py mock_provider.py   ← 新增，支撑双模式
  tools/                        # base.py fda_tools.py guideline_rag.py
  rag/                          # chunker.py retriever.py reranker.py index_builder.py  ← 新增
  memory/                       # patient_memory.py
  proactive/                    # scheduler.py
  safety/                       # rules_engine.py phi.py
  eval/                         # suite.py metrics.py datasets/
  audit/                        # logger.py
  db/                           # engine.py models.py(ORM) migrations/  ← 新增
```

## 3. 契约先行（跨任务依赖的精确接口，执行时不得擅自变更；变更走 ADR）

### 3.1 数据库 schema（PostgreSQL，M2 落地）

```sql
users(id uuid PK, username text UNIQUE, password_hash text, role text DEFAULT 'patient', created_at timestamptz)
patients(id uuid PK, external_ref text, risk_profile jsonb, created_at timestamptz)
sessions(id uuid PK, patient_id uuid FK, user_id uuid FK, thread_id text UNIQUE, title text, status text, created_at, updated_at)
messages(id uuid PK, session_id uuid FK, role text, content text, created_at)
citations(id uuid PK, message_id uuid FK, source text, doc_id text, snippet text, score float)
qc_rules(id uuid PK, version int, code text, description text, severity text, active bool, created_at)
qc_hits(id uuid PK, rule_id uuid FK, session_id uuid FK, payload jsonb, created_at)
audit_logs(id uuid PK, session_id uuid, user_id uuid, event_type text, payload jsonb, created_at)   -- 追加写
feedback(id uuid PK, session_id uuid, workbench_item_id text, original text, corrected text, label text, status text, note text, created_at)
eval_cases(id uuid PK, category text, prompt text, expected jsonb, tags text[])
eval_runs(id uuid PK, caseset_version text, metrics_json jsonb, report_path text, created_at)
patient_metrics(id uuid PK, patient_id uuid FK, date date, metric text, value float, unit text, flagged bool)
```

### 3.2 REST API（v1）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/v1/auth/login` | POST | `{username,password}` → `{token,user}` |
| `/v1/auth/me` | GET | 当前用户 |
| `/v1/sessions` | GET/POST | 会话列表 / 新建（`{title?}` → `{id,thread_id}`） |
| `/v1/chat/stream` | POST(SSE) | `{session_id,message}` → SSE 事件流（§3.3） |
| `/v1/reports/interpret` | POST | `{session_id,content}` → `{report_id,structured,summary,anomalies,citations}` |
| `/v1/patients/me` | GET | 患者档案 |
| `/v1/patients/me/metrics?days=90` | GET | `[{date,metric,value,unit,flagged}]` |
| `/v1/reminders` | GET | `[{id,type,message,due_at,status}]` |
| `/v1/workbench/queue?status=pending` | GET | 复核队列 `[{id,session_id,risk_level,summary,created_at}]` |
| `/v1/workbench/items/{id}` | GET | 复核详情：`{session_trace,draft,qc_result,patient_context}` |
| `/v1/workbench/items/{id}/review` | POST | `{decision:approve\|reject\|edit, corrected?,label?,note?}` → 写 feedback |
| `/v1/admin/metrics?range=7d` | GET | `{refuse_rate,leak_rate,faithfulness,compliance,hitl_rate,p95_ms}` |
| `/v1/admin/audit/sessions/{id}` | GET | `{trace:[TraceEvent]}` |
| `/v1/admin/rules` | GET/PUT | 规则列表 / 启停、改级别 |
| `/v1/admin/datasets` | GET/POST | 评测集列表 / 新增用例 |

### 3.3 SSE 事件协议（chat 流）

```
event: meta        data: {"session_id":"...","intent":"...","risk_level":"routine"}
event: token       data: {"text":"白细胞"}            # 流式增量
event: citation    data: {"index":0,"source":"FDA","snippet":"..."}
event: qc          data: {"status":"passed"|"hitl"|"refused","risk_score":0.2,"violations":[]}
event: correction  data: {"message":"..."}            # 方案C演进预留，M5 不要求
event: done        data: {"final":"...","citations":[...]}
event: error       data: {"code":"...","message":"..."}
```

前端 `services/chat.ts` 用 `fetch + ReadableStream` 解析（POST SSE 不能用 EventSource），按 `event:` / `data:` 行切分，事件名分发到回调。

### 3.4 AgentState（LangGraph，与 spec §7.1 一致）

```python
class AgentState(TypedDict):
    messages: Annotated[list, Messages]
    patient_id: str | None
    intent: str
    risk_level: str                     # routine | urgent | critical
    citations: list[Citation]
    draft: str
    qc_result: QCResult
    hitl_required: bool
```

### 3.5 LLM Provider 抽象（双模式核心）

```python
class LLMProvider(Protocol):
    def complete(self, *, messages: list[dict], temperature: float = 0.2) -> str: ...
    def stream(self, *, messages: list[dict]) -> Iterator[str]: ...

# RealProvider: 封装 langchain-openai（OpenAI/DeepSeek/Qwen 兼容端点，模型分级路由）
# MockProvider: 规则驱动返回预设结果，覆盖：正常问诊/报告解读/拒答/紧急转人工/多轮
```

`config.llm_mode = "mock" | "real"`，`make_provider()` 工厂按配置返回；Mock 结果可被 `tests/eval/datasets/` 校准，保证 CI 确定性。

---

## 4. 任务拆解（每任务：可独立测试交付，0.5–2 天）

### M0 工程骨架（1 周）

#### Task M0-1: 后端工程初始化
**Files:** Create `pyproject.toml`（已有，核对依赖）、`src/care_lifeline/config.py`、`src/care_lifeline/__init__.py`、`tests/unit/test_config.py`；Makefile 已存在，核对 `install/dev/test/lint/type` 可用。

**Interfaces:**
- Produces: `Settings`（pydantic-settings，字段：`llm_mode: Literal["mock","real"]="mock"`、`database_url: str`、`qc_risk_threshold: float=0.75`、`api_port:int=8000`）

- [ ] **Step 1**: `uv sync` 安装依赖；`uv run pytest tests/unit/test_config.py`（先写：断言 `Settings(llm_mode="mock")` 加载与默认值）
- [ ] **Step 2**: 确认测试失败（Settings 未定义）→ 实现 `config.py` → 通过
- [ ] **Step 3**: `make lint` / `make type` 通过；`pre-commit run --all-files` 通过
- [ ] **Step 4**: 征求用户同意后 `git commit -m "chore: 初始化工程配置与依赖"`

#### Task M0-2: 前端脚手架 + 设计 tokens
**Files:** Create `web/`（pnpm 创建 Vite react-ts 模板）、`web/src/styles/tokens.css`、`web/src/main.tsx`（Arco `ConfigProvider` 挂载主题）、删除模板残留。

- [ ] **Step 1**: `pnpm create vite web --template react-ts` → `pnpm add @arco-design/web-react zustand @tanstack/react-query recharts dayjs react-markdown remark-gfm ahooks react-router-dom`；`pnpm add -D vitest @testing-library/react jsdom`
- [ ] **Step 2**: tokens.css 写入 §6 色彩/间距/圆角 token；Arco 主题定制：`ConfigProvider componentConfig={{ Button: { shape: 'round' } }}` + 主题色 `#3370FF`
- [ ] **Step 3**: 页面骨架（浅灰背景 `#F7F8FA` + 白色内容卡），`pnpm dev` 可见干净的空壳页
- [ ] **Step 4**: commit `chore: 初始化前端脚手架与设计 tokens`

#### Task M0-3: 飞书式布局 + 路由骨架
**Files:** Create `web/src/layouts/AppLayout.tsx`、`web/src/app/router.tsx`、`web/src/pages/HomePage.tsx`（其余页面先放占位组件）、`web/src/pages/NotFoundPage.tsx`

- [ ] **Step 1**: AppLayout = 左侧导航（Logo 区 + Menu，items: 首页/智能问诊/报告解读/慢病管理/医生工作台/管理后台/设置）+ 顶栏（面包屑 + 用户菜单）；宽度 220/52，`position: sticky`
- [ ] **Step 2**: router 懒加载全部页面路由；`/login` 独立布局（无侧栏）
- [ ] **Step 3**: 验证：导航切换、刷新保持路由、404 页
- [ ] **Step 4**: commit `feat: 搭建飞书式布局与路由骨架`

#### Task M0-4: 前端请求层 + 契约类型
**Files:** Create `web/src/types/contract.ts`、`web/src/services/http.ts`、`web/src/services/api.ts`、`web/src/services/chat.ts`（SSE 解析器）、`web/src/stores/session.ts`

- [ ] **Step 1**: contract.ts 按 §3.2/3.3 定义 TS 类型（`ChatMessage/Citation/SSEEvent*/Session/AdminMetrics`）
- [ ] **Step 2**: http.ts 封装（baseURL `/v1`、Authorization 注入、401 跳登录、统一错误 toast）；api.ts 封装各端点
- [ ] **Step 3**: chat.ts 实现 SSE 解析：`fetch POST` → 逐行读 `event:`/`data:` → 回调分发；导出 `streamChat(sessionId, message, handlers)`
- [ ] **Step 4**: 单测（vitest）：给定 SSE 文本流，断言事件分发正确（含 token 拼接、error 事件）
- [ ] **Step 5**: commit `feat: 前端请求层与 SSE 流式客户端`

**M0 出口验证**：`make dev` + `cd web && pnpm dev` 双端可跑；CI 双端绿（前端加 `web` job：`pnpm build` + vitest）。

---

### M1 最小图 + 流式 API（1.5 周）

#### Task M1-1: LLM Provider 抽象
**Files:** Create `src/care_lifeline/llm/provider.py`、`real_provider.py`、`mock_provider.py`、`tests/unit/test_mock_provider.py`

- [ ] **Step 1**: 测试：`MockProvider().complete(messages=[...])` 返回非空 str；`stream()` 产出 ≥1 个 chunk；mock 命中"胸痛"关键词时输出含"急诊"提示
- [ ] **Step 2**: provider.py 定义协议 + `make_provider(settings)` 工厂；mock_provider.py 按 intent 预设（问诊/报告/拒答/紧急），内容真实感（医学示例数据）
- [ ] **Step 3**: real_provider.py 封装 `langchain-openai`（`model_mini`/`model_flagship` 分级）；未配 key 时 `real` 模式启动报错并提示 `LLM_MODE=mock`
- [ ] **Step 4**: commit `feat: 实现 LLM Provider 双模式抽象`

#### Task M1-2: LangGraph 最小图
**Files:** Create `src/care_lifeline/graph/state.py`、`builder.py`、`nodes/{router,triage,report_interpreter,qc,responder}.py`、`tests/unit/test_graph.py`

**Interfaces:**
- Consumes: `make_provider()`
- Produces: `build_graph() -> CompiledGraph`；节点函数签名 `node(state: AgentState) -> dict`（返回部分更新）

- [ ] **Step 1**: 测试：给定"最近化验单说贫血"输入，图执行后 state 含 `draft` 非空、`citations` 非空、`qc_result.status=="passed"`；"我胸痛" → `hitl_required=True`
- [ ] **Step 2**: state.py 定义 AgentState；router/triage 用 mock provider 定 intent/risk_level（规则词兜底紧急词）
- [ ] **Step 3**: report_interpreter 生成带引用的解读草稿；qc 节点（先只做规则雏形 + 占位 LLM 层）；responder 拼装免责声明
- [ ] **Step 4**: builder 用 `StateGraph` 串接 + 条件边（risk_level=critical → hitl）；测试通过
- [ ] **Step 5**: commit `feat: 打通 LangGraph 最小诊疗图`

#### Task M1-3: SSE 流式端点
**Files:** Create `src/care_lifeline/api/main.py`、`routers/chat.py`、`tests/eval/test_chat_stream.py`（httpx + ASGI 测试）

**Interfaces:**
- Consumes: `build_graph()`；Produces: `POST /v1/chat/stream`

- [ ] **Step 1**: 测试：SSE 响应按序包含 `event: meta` → `token`（≥1）→ `qc` → `done`；非法输入返回 `error` 事件
- [ ] **Step 2**: 实现流式端点：`StreamingResponse` + `media_type="text/event-stream"`；图执行按节点产出转 token 事件（M1 简化：responder 的 mock stream 直接发 token，QC 结果发 qc 事件）
- [ ] **Step 3**: `/v1/health` 探活；commit `feat: 实现 SSE 流式问诊端点`

#### Task M1-4: 对话页（流式渲染）
**Files:** Create `web/src/pages/ChatPage.tsx`、`web/src/hooks/useChatStream.ts`、`web/src/components/{StreamMessage,CitationCard,Markdown,EmptyState}.tsx`

- [ ] **Step 1**: useChatStream 封装：发送消息 → 建会话（若空）→ `streamChat` 回调更新 messages（token 累积到当前 assistant 消息）
- [ ] **Step 2**: ChatPage：左侧会话列表（新建/切换）+ 右侧消息流；输入框 Enter 发送、loading 态禁用
- [ ] **Step 3**: StreamMessage 渲染：Markdown（react-markdown + remark-gfm）+ 引用角标（`[1]` 点击展开 CitationCard）+ 质控徽标（passed=正常/hitl=转人工高亮/refused=拒答灰）；Qc 事件触发风险等级提示条
- [ ] **Step 4**: 验证（mock 模式）：完整问诊流式展示、引用可点、转人工场景出现提示；commit `feat: 实现流式问诊对话页`

**M1 出口验证**：`LLM_MODE=mock make dev` + 前端对话页完成一次"描述症状→分诊→解读→引用→免责"全流程。

---

### M2 质控 + 持久化 + 鉴权（2 周）

#### Task M2-1: 质控规则引擎（核心，覆盖率 100%）
**Files:** Create `src/care_lifeline/safety/rules_engine.py`、`tests/unit/qc_rules/test_rules_engine.py`

**Interfaces:**
- Produces: `Rule`（dataclass：`code/description/severity/evaluate(draft, ctx)->Violation|None`）、`Violation(code,severity,message)`、`load_ruleset(version)`（内置 v1 规则集）、`evaluate_all(rules, draft, ctx) -> list[Violation]`

- [ ] **Step 1**: 测试先行（≥12 条，覆盖 100%）：越界请求拒答（"帮我开处方"→ blocking）、紧急词（胸痛/呼吸困难/卒中征兆→ blocking + 转人工）、缺免责声明→warning、缺引用→warning、正常输出→通过
- [ ] **Step 2**: 实现纯函数规则集 v1（无 IO、无 LLM）；`evaluate_all` 聚合；severity=blocking 短路
- [ ] **Step 3**: `coverage run -m pytest tests/unit/qc_rules/ && coverage report --fail-under=100`；commit `feat: 实现质控规则引擎 v1（单测100%）`

#### Task M2-2: PHI 脱敏中间件
**Files:** Create `src/care_lifeline/safety/phi.py`、`src/care_lifeline/api/middleware/phi.py`、`tests/unit/test_phi.py`

- [ ] **Step 1**: 测试：姓名/身份证号/手机号/病历号被替换为 `[PHI]`；普通文本不变；脱敏幂等
- [ ] **Step 2**: 实现（正则 + 简单 NER 规则）；FastAPI 中间件对请求体先脱敏再进路由，响应/日志只记脱敏后文本
- [ ] **Step 3**: commit `feat: 实现 PHI 脱敏中间件`

#### Task M2-3: LLM QC 节点 + 阈值配置
**Files:** Modify `nodes/qc.py`、`config.py`；Create `tests/unit/qc_rules/test_llm_reviewer.py`

- [ ] **Step 1**: 测试：mock LLM 返回高风险分（>阈值）→ `hitl_required=True`；低风险 → 通过
- [ ] **Step 2**: 实现 `LLMReviewer.check(draft, evidence) -> QCResult{status,risk_score,violations}`；阈值读 `settings.qc_risk_threshold`（mock 模式下返回确定性分数，便于测试）
- [ ] **Step 3**: commit `feat: 实现 LLM 语义评审层`

#### Task M2-4: PostgresSaver + 会话/审计持久化
**Files:** Create `src/care_lifeline/db/engine.py`、`models.py`、`migrations/001_init.sql`；Modify `graph/builder.py`（挂 Checkpointer）、`api/routers/sessions.py`；Create `tests/eval/test_persistence.py`（用测试库）

- [ ] **Step 1**: models.py 定义 §3.1 表（SQLAlchemy 2.0 + async）；migrations 建表脚本
- [ ] **Step 2**: `make compose-up`（postgres 起）；builder 使用 `PostgresSaver`，`thread_id=sessions.thread_id`
- [ ] **Step 3**: 测试：同一 thread_id 第二次调用可恢复上下文；`audit_logs` 追加写入可见
- [ ] **Step 4**: commit `feat: 接入 Postgres Checkpointer 与会话持久化`

#### Task M2-5: 用户模型 + JWT 鉴权
**Files:** Create `src/care_lifeline/api/auth.py`、`tests/eval/test_auth.py`；Create 种子数据（admin/doctor/patient 三个演示账号，bcrypt 哈希）

- [ ] **Step 1**: 测试：login 正确返回 token；无 token 访问 `/v1/sessions` → 401；角色（doctor 才能访问 workbench）
- [ ] **Step 2**: 实现 auth（python-jose + passlib/bcrypt）、依赖注入 `get_current_user`、router 级权限
- [ ] **Step 3**: commit `feat: 实现 JWT 鉴权与角色权限`

#### Task M2-6: HITL 中断/恢复
**Files:** Modify `graph/builder.py`、`nodes/hitl.py`、`api/routers/chat.py`；Create `tests/eval/test_hitl.py`

- [ ] **Step 1**: 测试：high-risk 会话进入 pending 状态，医生 `review(approve)` 后会话继续输出最终结果
- [ ] **Step 2**: 实现：`interrupt()` 挂起 → feedback 表生成 workbench 项 → review 后 `update_state` 恢复执行
- [ ] **Step 3**: commit `feat: 实现 HITL 中断与人工恢复`

#### Task M2-7: 登录页 + 会话管理
**Files:** Create `web/src/pages/LoginPage.tsx`；Modify `stores/session.ts`、`services/api.ts`、`AppLayout`（用户菜单/退出）

- [ ] **Step 1**: LoginPage：账号密码表单（演示账号提示文案），成功存 token 跳首页；401 全局跳登录
- [ ] **Step 2**: 会话管理：首页/侧栏列出历史会话，新建会话，点击恢复（thread_id 传入 chat）
- [ ] **Step 3**: 验证：登录态持久化（localStorage）、会话列表切换；commit `feat: 实现登录与会话管理`

**M2 出口验证**：登录 → 问诊（mock）→ 会话断线后从列表恢复继续对话；`coverage` 中 qc_rules 100%。

---

### M3 报告解读 + 慢病管理（2 周）

#### Task M3-1: RAG 管线
**Files:** Create `src/care_lifeline/rag/{chunker,retriever,reranker,index_builder}.py`、`data/knowledge/`（指南中文示例 5–8 篇，如高血压/糖尿病指南节选）、`tests/unit/test_rag.py`

- [ ] **Step 1**: 测试：中文文本按语义边界分块（≤500 字）；混合检索（BM25+向量）对"高血压 目标值"召回相关块；rerank 后 top3 变化合理
- [ ] **Step 2**: 实现 chunker（按标题/段落边界）、retriever（Qdrant 向量 + BM25 融合）、reranker（CrossEncoder MiniLM）、index_builder（建库脚本 + `make index`）
- [ ] **Step 3**: commit `feat: 实现指南 RAG 管线`

#### Task M3-2: 报告解读（结构化）
**Files:** Modify `nodes/report_interpreter.py`；Create `src/care_lifeline/tools/lab_parser.py`、`tests/eval/test_report_interpreter.py`、`data/samples/reports/`（3 份中文示例报告）

- [ ] **Step 1**: 测试：输入一份血常规文本报告 → 输出结构化指标 `[{name,value,unit,ref_range,status:normal|high|low,explanation}]` + 异常项标记 + 通俗小结 + 引用
- [ ] **Step 2**: 实现 lab_parser（mock 模式用规则解析；real 模式 LLM 结构化输出 + 规则校验兜底）
- [ ] **Step 3**: `/v1/reports/interpret` 端点 + 单测；commit `feat: 实现化验单结构化解读`

#### Task M3-3: 患者记忆 + 指标存储
**Files:** Create `src/care_lifeline/memory/patient_memory.py`、`api/routers/patient.py`、`tests/eval/test_patient_metrics.py`

- [ ] **Step 1**: 测试：写入连续血糖/血压指标 → `patient_context` 拼装含近期趋势摘要；越界值 flagged=true
- [ ] **Step 2**: 实现 memory 读写（脱敏字段）、`/v1/patients/me`、`/v1/patients/me/metrics`
- [ ] **Step 3**: commit `feat: 实现患者纵向记忆与指标存储`

#### Task M3-4: Proactive 最小触发
**Files:** Create `src/care_lifeline/proactive/scheduler.py`、`tests/eval/test_proactive.py`

- [ ] **Step 1**: 测试：模拟连续 3 天空腹血糖 >7.0 → 生成"建议就医/复测"提醒并标记需要人工确认
- [ ] **Step 2**: 实现：APScheduler 每日任务扫描 `patient_metrics` 越界规律 → 写 `reminders`；`/v1/reminders`
- [ ] **Step 3**: commit `feat: 实现慢病异常主动提醒`

#### Task M3-5: 报告解读页
**Files:** Create `web/src/pages/ReportPage.tsx`、`web/src/components/Uploader.tsx`

- [ ] **Step 1**: 粘贴或上传文本报告 → 调 `/v1/reports/interpret` → 结构化表格展示（指标名/结果/参考范围/状态徽标 正常=绿 偏高=红 偏低=橙）+ 异常摘要卡片 + 引用
- [ ] **Step 2**: 演示数据入口（"填入示例报告"按钮，加载 `data/samples` 对应内容，便于面试演示）
- [ ] **Step 3**: commit `feat: 实现报告解读页`

#### Task M3-6: 慢病管理面板
**Files:** Create `web/src/pages/ChronicPage.tsx`、`web/src/components/TrendChart.tsx`

- [ ] **Step 1**: 指标趋势图（Recharts 折线：血糖/血压，超阈值点红标）；最近指标卡片（较上次升降）
- [ ] **Step 2**: 提醒列表（/v1/reminders：类型徽标 + 时间 + 状态）；"主动随访"演示区（触发一次 mock 随访，展示 Proactive 叙事）
- [ ] **Step 3**: commit `feat: 实现慢病管理面板`

**M3 出口验证**：粘贴示例报告 → 结构化解读 + 异常标注 + 引用；慢病面板展示趋势图与提醒。

---

### M4 HITL 工作台 + 管理后台（2 周）

#### Task M4-1: 复核队列 API
**Files:** Create `src/care_lifeline/api/routers/workbench.py`、`tests/eval/test_workbench.py`

- [ ] **Step 1**: 测试：pending 队列分页；详情返回完整轨迹（input→draft→qc→violations→patient_context）；review 三种决策落 feedback
- [ ] **Step 2**: 实现 `GET /queue`、`GET /items/{id}`、`POST /items/{id}/review`（decision=approve/reject/edit；edit 时保存 corrected）
- [ ] **Step 3**: commit `feat: 实现医生复核队列 API`

#### Task M4-2: 反馈→规则/用例沉淀脚本
**Files:** Create `src/care_lifeline/eval/promote.py`、`tests/eval/test_promote.py`

- [ ] **Step 1**: 测试：被拒且标注"应拒答"的 feedback → 生成 eval_cases 草稿；出现 ≥3 次同模式的反馈 → 输出候选规则（code 建议）
- [ ] **Step 2**: 实现沉淀脚本（生成 JSON 草稿，人工确认后入集——**不自动写入 eval_cases 生产集**）
- [ ] **Step 3**: commit `feat: 实现反馈沉淀为评测用例与候选规则`

#### Task M4-3: 评测运行 + 审计 + 规则 API
**Files:** Create `src/care_lifeline/api/routers/admin.py`、`tests/eval/test_admin_api.py`

- [ ] **Step 1**: 测试：`/v1/admin/metrics` 返回结构完整；audit 回放含完整轨迹；rules 启停生效
- [ ] **Step 2**: 实现：metrics 从 `eval_runs`/观测聚合；audit 查询；rules CRUD（启停/级别）
- [ ] **Step 3**: commit `feat: 实现管理后台 API`

#### Task M4-4: HITL 工作台
**Files:** Create `web/src/pages/WorkbenchPage.tsx`、`web/src/components/AuditTimeline.tsx`

- [ ] **Step 1**: 队列表格（风险等级/摘要/时间/状态，紧凑密度）；点击进详情
- [ ] **Step 2**: 详情：左侧原对话回放（AuditTimeline 时间线：每跳决策/工具/引用/质控）+ 右侧质控结果 + 操作区（通过/驳回/修改后通过 + 标签 + 备注）
- [ ] **Step 3**: 验证：review 后队列状态更新；commit `feat: 实现医生复核工作台`

#### Task M4-5: 管理后台
**Files:** Create `web/src/pages/AdminPage.tsx`（Tab 布局）

- [ ] **Step 1**: 评测看板 Tab：指标卡片（拒答率/误放行率/faithfulness/compliance/转人工率/P95）+ 趋势（近 7 次 eval_runs）+ 对照 §9.2 基线标色
- [ ] **Step 2**: 审计回放 Tab：按会话查询 → AuditTimeline；规则配置 Tab：列表/启停/级别编辑
- [ ] **Step 3**: 数据集 Tab：红队集/拒答集用例列表 + 新增（复用沉淀脚本输出导入）；commit `feat: 实现管理后台`

**M4 出口验证**：触发一个 high-risk 场景 → 工作台出现待复核 → 医生驳回/通过 → 会话状态更新；反馈出现在数据集 Tab。

---

### M5 评测 + 部署 + 打磨（1.5 周）

#### Task M5-1: 评测套件完整化
**Files:** Modify `eval/suite.py`、`metrics.py`；Create `tests/eval/test_metrics.py`、`data/eval/redteam.json`（≥20 条诱导违规）、`data/eval/refusal.json`（≥15 条）、`data/eval/report_cases.json`（≥10 条）

- [ ] **Step 1**: 测试：`run_suite()` 对 mock 模式产出全部 §9.1 指标且数值确定（CI 可断言）
- [ ] **Step 2**: 实现：拒答率/误放行率（规则判定）、faithfulness（ragas 或 mock 简化——mock 下用自研 groundedness 规则）、compliance、转人工率
- [ ] **Step 3**: 跑 `make eval` 输出 Markdown 报告，与 §9.2 MVP 基线对照（不达标项记录为下一迭代输入）；commit `feat: 评测套件与基线报告`

#### Task M5-2: 评测回归 CI
**Files:** Modify `.github/workflows/eval.yml`（跑 `make eval`，上传报告 artifact + PR comment）

- [ ] **Step 1**: eval.yml 在 `workflow_dispatch` / PR 带 `eval` label 时运行，产物 `eval-report.md` 上传
- [ ] **Step 2**: 验证（本地 act 或推送演示分支）：workflow 触发并产出报告；commit `ci: 评测回归流水线`

#### Task M5-3: Docker Compose 全栈编排
**Files:** Create `docker-compose.yml`（web/api/postgres/qdrant）、`web/Dockerfile`（nginx 托管构建产物 + 反代 `/v1`）、`scripts/seed_demo.sh`（演示账号 + 示例报告 + 指南语料索引）、Modify 根 `Dockerfile`、`Makefile`（`make up` = 全栈一键）

- [ ] **Step 1**: 后端镜像（uv + 依赖 + 启动 API）；前端镜像（`pnpm build` → nginx serve + proxy `/v1→api`）
- [ ] **Step 2**: compose：postgres 健康检查 → api 依赖就绪 → web；卷持久化 pg/qdrant
- [ ] **Step 3**: `scripts/seed_demo.sh` 初始化演示数据；`make up` 后浏览器打开 localhost 完成演示全流程
- [ ] **Step 4**: commit `feat: Docker Compose 全栈一键部署`

#### Task M5-4: 前端打磨
**Files:** Modify `web/src/styles/tokens.css`、各页面空态/加载/错误态、`web/vite.config.ts`（分包/压缩）

- [ ] **Step 1**: 全页面补：骨架屏（skeleton）、空状态（EmptyState 统一插画+引导文案）、错误态（重试按钮）、loading 按钮
- [ ] **Step 2**: 细节：表格紧凑密度统一、响应式（≥1200 三栏/中窄屏两栏）、动效 150–250ms、焦点样式
- [ ] **Step 3**: 性能：`pnpm build` 产物分包（vendors/pages 懒加载 chunk）、Lighthouse 走查
- [ ] **Step 4**: commit `style: 全站打磨与构建优化`

**M5 出口验证**：`make up` 一键起全栈 → 演示账号登录 → 问诊/报告/慢病/工作台/管理后台全流程可走通；`make eval` 输出基线报告。

---

### P2 可选项（不进主线，按时间推进）

- 药盒识别：图像上传端点 + PillboxVision 节点 + 前端上传组件（工具已预留）。
- 方案 C 流式质控：规则层前置实时拦截 + LLM 后验 + `correction` 事件前端处理。
- 语义缓存：同患者同主诉命中缓存，省 token。
- Proactive 事件驱动：DB 变更捕获替代轮询；分布式锁。

## 5. 执行顺序与依赖

```
M0-1 → M0-2(M0-3, M0-4 可并行) → M1-1 → M1-2 → M1-3 → M1-4
M2 内部：M2-1/M2-2 可先行；M2-3 依赖 M1-1；M2-4 依赖 M2-1；M2-5/M2-6 可并行；前端任务依赖对应后端 API
M3：M3-1 → M3-2 → M3-3 → M3-4（后端）；前端 M3-5/M3-6 依赖 M3-2/M3-3/M3-4
M4：M4-1 → M4-2 → M4-3（后端）；前端 M4-4/M4-5 依赖对应 API
M5：M5-1 → M5-2 → M5-3 → M5-4（M5-4 可随时并行）
```

## 6. 前端设计规范（不 AI 味）

### 6.1 原则

- **克制**：低饱和、高信息密度、专业医疗感；不做装饰性特效。
- **一致性**：所有页面复用 tokens 与组件，不各写风格。
- **真实感**：示例数据用真实医学格式（如 `WBC 6.5 ×10⁹/L (3.5–9.5)`），文案像真实产品而非宣传语。

### 6.2 设计 tokens（tokens.css）

```css
:root {
  --brand-500: #3370FF;        /* 飞书蓝系，主操作 */
  --brand-100: #E8F3FF;        /* 选中背景 */
  --success: #00B42A;          /* 正常/低危 */
  --danger: #F53F3F;           /* 异常/高危（医疗语境红=危险） */
  --warning: #FF7D00;          /* 中危/待复核 */
  --bg-page: #F7F8FA;          /* 页面浅灰底 */
  --bg-card: #FFFFFF;
  --text-1: #1D2129; --text-2: #4E5969; --text-3: #86909C;
  --radius-sm: 4px; --radius-md: 8px;
  --shadow-card: 0 1px 2px rgba(0,0,0,.06);
  --font: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
}
```

### 6.3 布局与组件

- 布局：左侧导航 220px（图标+文字，选中项 `--brand-100` 底 + 蓝字）+ 顶栏 52px + 内容区白卡在浅灰底。
- 表格：Arco `size="small"`、斑马纹、表头 13px 中灰；列表行 hover 蓝底。
- 卡片圆角 8px、阴影极轻；**禁止**渐变/发光/霓虹/紫色系。
- 动效 150–250ms `ease`，仅 hover/切换/展开。
- 空态：简洁插画（Arco 内置）+ 一句话引导 + 主按钮，**不用 emoji 装饰**。
- 加载：骨架屏优先，转圈仅用于按钮等待。

### 6.4 文案规范（产品化，非"AI 味"）

| ❌ 避免 | ✅ 使用 |
|---|---|
| "AI 智能助手为您服务" | "智能问诊" / 页面标题 |
| "我是 AI，可以帮您…" | 直接提供功能入口与表单 |
| "探索无限可能" | "上传报告，查看异常项" |
| emoji 表情点缀 | 语义图标（Arco Icon） |

### 6.5 不 AI 味自检清单（每次页面完成时过一遍）

- [ ] 无紫色/渐变/霓虹；主色为医疗蓝
- [ ] 无 emoji 装饰；图标全部 Arco Icon
- [ ] 文案是产品语气，无"AI 助手"式空话
- [ ] 示例数据真实医学格式，非占位 lorem
- [ ] 信息密度对齐飞书（表格紧凑、卡片克制）
- [ ] 空/错/加载三态齐全

## 7. 整体验收标准

1. `make up` 一键启动全栈，无手动步骤（演示账号：`admin/doctor/patient` + 统一演示密码）。
2. `LLM_MODE=mock` 全流程可跑（问诊/报告/慢病/工作台/管理后台），**不依赖任何外部 API**。
3. 配置真实 key（`LLM_MODE=real`）后效果真实可信。
4. `make check` 全绿（lint+type+test）；`make eval` 输出基线报告并对照 §9.2。
5. 质控规则单测覆盖率 100%；审计链路完整可回放。
6. 面试叙事点全部可演示：多 Agent 分级诊疗 / 质控双层把关 / 会话恢复与时间旅行 / 流式×质控 / 反馈飞轮 / 评测基线。

## 8. 风险与依赖

| 风险 | 缓解 |
|---|---|
| 中文 SSE 流式解析（token 被截断） | 前端按 `event:`/`data:` 行解析 + 文本累积不按字符边界处理；后端 chunk 不切半个 token |
| Mock LLM 覆盖面不足 | 场景表按 intent/紧急词/报告模板组织，与 eval 数据集同源校准 |
| Arco 定制工作量大 | 只用主题 token + 少量全局覆写，不深改组件 |
| 中文指南分块质量 | chunker 按标题/段落边界 + 实测调参；`data/knowledge` 选结构化文本 |
| 报告结构化解析（real 模式） | LLM 输出 JSON schema 校验 + 规则兜底回退 |
| 10 周周期 | M0–M3 交付即可独立演示；P2 严格切割 |

---

*计划结束。执行中如需偏离 §3 契约，必须先新增 ADR 再改代码。*
