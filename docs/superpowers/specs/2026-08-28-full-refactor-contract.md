# 全量重构契约 Spec（v1）

> 日期：2026-08-28　|　授权：可破坏性重构　|　第一原则：**保证可用**
> 本文件是三个并行开发线（后端核心 / 后端外围 / 前端）的**唯一契约依据**。任何跨模块改动必须以本文件为准；若需偏离，先改本文件。

---

## 0. 决策前提（用户已确认）

| 决策 | 选择 |
|---|---|
| 前端路线 | **重做 React SPA，删除 `api/static/index.html` 及回退逻辑**，只保留一套 UI |
| 修复范围 | **P0 + P1 + P2 全量** |
| LLM 模式 | **mock 优先（零外部依赖可完整演示、CI 可跑），real 可切**（填 `CARE_LLM_API_KEY` 即生效） |

---

## 1. 统一错误响应结构（P2-12）

**所有 HTTP 错误一律返回：**

```json
{ "code": "string_snake_case", "message": "人类可读中文", "detail": {} }
```

- `detail` 可选，用于承载结构化上下文
- 禁止再出现 `detail="裸字符串"`
- 实现：在 `api/app.py` 注册全局 `@app.exception_handler(HTTPException)` + `@app.exception_handler(RequestValidationError)` + `@app.exception_handler(Exception)`
- 401 保留 `WWW-Authenticate: Bearer` 头

**SSE 端点内的错误**仍走 `event: error` + `data: {"code","message"}`，但空输入等客户端错误改为**先返回 4xx**，不再用 HTTP 200 包错误事件。

既有 code 枚举（可扩展）：

| code | HTTP | 语义 |
|---|---|---|
| `unauthorized` | 401 | 未登录 / token 无效 |
| `forbidden` | 403 | 角色权限不足 |
| `invalid_credentials` | 401 | 用户名或密码错误 |
| `not_found` | 404 | 资源不存在 |
| `invalid_request` | 400 | 参数非法 |
| `internal_error` | 500 | 未捕获异常（**日志记 traceback，响应不泄露细节**） |

---

## 2. Scope Classifier（P0 根因，最关键）

### 2.1 问题

当前系统没有任何机制判断"这是不是医疗问题"。35 条应拒答用例泄漏 26 条：
- 非医疗类（星座运势 / 快速排序 / 写情书 / 入侵服务器）**15/15 全泄漏**
- 越权医疗类（开处方 / 下诊断 / 判断肿瘤良恶性）**大部分泄漏**
- 安全类（自杀 / 违法）**无兜底**

现质控规则查的是**模型回复 draft** 里有没有「开处方/开药/诊断结论」——模型永不输出这些词，故永不命中。

### 2.2 契约

**新增模块 `src/care_lifeline/safety/scope.py`**，导出：

```python
class ScopeVerdict(StrEnum):
    IN_SCOPE = "in_scope"           # 正常医疗咨询，继续走图
    OUT_OF_SCOPE = "out_of_scope"   # 非医疗问题 → 拒答
    RESTRICTED = "restricted"       # 越权医疗请求（开处方/下诊断/开证明）→ 拒答
    UNSAFE = "unsafe"               # 自杀/自伤/违法 → 拒答 + 强提示

@dataclass
class ScopeResult:
    verdict: ScopeVerdict
    reason: str                     # 人类可读原因，进审计与 SSE
    matched: str | None = None      # 命中的规则/关键词

def classify_scope(user_text: str, provider: LLMProvider | None = None) -> ScopeResult
```

**判定顺序（短路返回，优先级从高到低）：**

1. **`UNSAFE`** — 自杀 / 自伤 / 伤害他人 / 违法（入侵、毒品、管制药品）。纯规则词表，必须命中。
2. **`OUT_OF_SCOPE`** — 非医疗意图。规则词表 + LLM 兜底：
   - 规则：明显非医疗关键词（星座 / 运势 / 写代码 / 小说 / 股票 / 天气 / 翻译 / 菜谱 / 笑话 / 情书 / 生成图片 / 入侵 / 服务器 …）
   - LLM（`provider` 非空且 `llm_mode == "real"` 时）：结构化判 `is_medical: bool`；**LLM 判否 → OUT_OF_SCOPE**
   - mock 模式下**只跑规则**（保证零依赖可测）
3. **`RESTRICTED`** — 越权医疗请求。规则：`开.{0,6}(处方|药)|下.{0,3}诊断|诊断.{0,3}(结论|证明|书)|出具.{0,4}(证明|鉴定|报告)|开.{0,4}抗生素|判断.{0,4}(良|恶)性`
   - **注意用宽松正则，覆盖「开降压药处方」这类不连续表述**
4. 其余 → `IN_SCOPE`

**要求：**
- 规则词表抽成模块级命名常量，与 `router.py` 现有 `EMERGENCY_KEYWORDS` 等**合并到一处共享**（`safety/keywords.py`），消除 DRY 违规（P2-20）
- 单测覆盖每一个 verdict 分支，**`tests/unit/safety/test_scope.py`**
- 必须能让 `data/eval/refusal.json` 15 条 + `redteam.json` 中非急症条**全部**判为非 `IN_SCOPE`

### 2.3 接入位置

`router_node`（`graph/nodes/router.py`）**第一步**就调 `classify_scope()`：

```python
scope = classify_scope(user_text, provider)
if scope.verdict != ScopeVerdict.IN_SCOPE:
    return {
        "intent": "refuse",           # 新增 intent 取值
        "risk_level": "critical" if scope.verdict == ScopeVerdict.UNSAFE else "routine",
        "scope_result": scope,
        "hitl_required": False,
    }
```

`AgentState` 新增字段：`scope_result: ScopeResult | None`。

条件边增加分支：`intent == "refuse"` → 走 `refuse` 节点（新节点，产出拒答文案 + 原因）→ `qc` → `responder`。

### 2.4 质控规则方向修正（P0-3）

`safety/rules_engine.py` 的 `off_scope` 规则**改为消费 `ctx["scope_verdict"]`**，不再匹配 draft 里的黑名单词：

```python
# 伪代码
if ctx.get("scope_verdict") in (OUT_OF_SCOPE, RESTRICTED, UNSAFE):
    return Violation(code=f"scope_{verdict}", severity=BLOCKING, message=scope.reason)
```

`qc_node` 传入 `ctx={"risk_level":..., "scope_verdict":...}`。

保留并新增规则（目标 ≥8 条）：

| code | 级别 | 说明 |
|---|---|---|
| `scope_out_of_scope` | BLOCKING | 非医疗请求 |
| `scope_restricted` | BLOCKING | 越权医疗请求 |
| `scope_unsafe` | BLOCKING | 自杀/违法 |
| `emergency` | BLOCKING | 高危症状（保留，扩展词表） |
| `prescription_leak` | BLOCKING | **回复中出现具体药品剂量/用法**（防模型绕过） |
| `diagnosis_leak` | BLOCKING | 回复中出现确定性诊断措辞（「您患有」「确诊为」） |
| `missing_disclaimer` | WARNING | 保留 |
| `missing_citation` | WARNING | 保留 |

---

## 3. AgentState 契约（`graph/state.py`）

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    patient_id: str | None              # 本次要真正接上（P1-7）
    intent: str                         # emergency|medication|report|triage|refuse
    risk_level: str                     # routine|urgent|critical
    scope_result: ScopeResult | None    # 新增
    citations: list[Citation]
    draft: str
    qc_result: QCResult | None
    hitl_required: bool
    report: ReportResult | None
    medication_warnings: list[str]
    retry_count: int                    # 新增，Agent 循环用
    memory_context: str                 # 新增，患者纵向记忆注入
```

---

## 4. Agent 真循环（P1-6）

图从 DAG 改为**带条件回边的循环图**：

```
START → scope_check → router →[意图分发]→ {hitl|refuse|triage|report_interpreter|medication}
                                              ↓
                                             qc
                                              ↓
                              ┌───── status == warning 且 retry_count < 2 ─────┐
                              ↓                                               │
                          rewrite（重写 draft）───────────────────────────────┘
                              ↓ status passed/hitl/refused
                          responder → END
```

- `retry_count` 在 `rewrite` 节点 +1
- 上限常量 `_MAX_RETRY = 2`（`graph/builder.py` 模块级命名常量）
- 编译图时传 `recursion_limit` 兜底
- **必须保证不会无限循环**：单测 `tests/unit/test_graph_loop.py` 覆盖「连续 warning 也能在 3 步内结束」

### 4.1 interrupt 真 HITL（P1-6）

- Postgres 模式下（`checkpointer` 非 None）用 `langgraph.types.interrupt()` 在 `hitl` 节点暂停
- 恢复端点：`POST /v1/hitl/resume`，body `{session_id, decision, corrected_text?}` → `Command(resume=...)`
- SQLite 或无 checkpointer 时**降级为现有软 HITL**（保证可用，不阻塞）
- 保留 `/v1/workbench/*` 端点不变

---

## 5. Tool 协议（P2-4 / P2-13）

**新增 `src/care_lifeline/tools/base.py`**，定义统一 Tool 协议并接入 LangGraph：

```python
@dataclass
class ToolResult:
    ok: bool
    data: dict
    citations: list[Citation]
    error: str | None = None

class CareTool(Protocol):
    name: str
    description: str
    async def run(self, **kwargs) -> ToolResult: ...
```

现有能力改造为 Tool（**保持向后兼容，现有节点直接调用不受影响**）：
- `GuidelineSearchTool`（包装 `build_report_retriever()`）
- `ReportParseTool`（包装 `ReportInterpreter`）
- `DrugInteractionTool`（包装 `MedicationAgent`）
- `MetricTrendTool`（包装 `patient_memory`）

新增 `tools/registry.py::ALL_TOOLS`。**是否让 LLM 自主选工具由 `llm_mode` 决定**：real 模式可启用 tool-calling 分支；mock 模式走确定性节点调用。

---

## 6. RBAC（P0-4）

`User.role` 取值：`admin` / `clinician` / `patient`（默认 `patient`）。

`CurrentUser` 增加 `role: str`。新增 `api/security.py::require_roles(*roles)` 依赖工厂。

| 端点前缀 | 允许角色 |
|---|---|
| `/v1/admin/*` | `admin` |
| `/v1/workbench/*`、`/v1/hitl/*` | `clinician`、`admin` |
| 其余 | 任意已登录 |

- 种子用户扩展为 3 个（见 §8）
- `403` 返回 `{"code":"forbidden",...}`
- 单测 `tests/unit/test_rbac.py` 覆盖每个角色越权与放行

---

## 7. 前端 API 契约（前端按此开发，后端按此实现）

Base：`/v1`（Vite dev 已配 proxy）。所有请求 `Authorization: Bearer <token>`。

### 7.1 鉴权

```
POST /v1/auth/login
  body: {username, password}            ← 后端改为接收 JSON（前端已按 JSON 发）
  resp: {access_token, token_type, username, role}
```

> ⚠️ 后端**改为同时接受 JSON 与 form**（`OAuth2PasswordRequestForm` 或 Pydantic model），消除 P2-22 契约不一致。

```
POST /v1/auth/register   body:{username,password,role?}  resp:{access_token,...,role}
GET  /v1/auth/me         resp:{id, username, role}
```

### 7.2 对话

```
GET  /v1/sessions                       resp: SessionItem[]
POST /v1/sessions                       body:{title?}  resp: SessionItem
DELETE /v1/sessions/{session_id}        resp: {ok:true}
GET  /v1/sessions/{session_id}/messages resp: MessageItem[]     ← 新增
POST /v1/chat/stream                    body:{session_id, message}
```

SSE 事件（在现有 6 种基础上**新增 3 种**）：

| event | 载荷 | 说明 |
|---|---|---|
| `meta` | `{session_id,intent,risk_level,scope_verdict?}` | 增加 `scope_verdict` |
| `token` | `{text}` | |
| `citation` | `{index,source,snippet}` | |
| `hitl` | `{reason}` | |
| `qc` | `{status,risk_score,violations}` | |
| `done` | `{final,citations}` | |
| `error` | `{code,message}` | |
| **`agent_step`** | `{node,detail}` | 新增：Agent 节点流转可视化 |
| **`tool_call`** | `{tool,args_preview,ok}` | 新增：工具调用可视化 |
| **`memory`** | `{patient_id,metrics_used}` | 新增：记忆注入可视化 |

### 7.3 报告

```
POST /v1/report/interpret   body:{text}  resp:{fields:[{name,value,reference,abnormal}],citations}
```

**P1-11 修复**：必须支持一行多指标（「血压：150/95…，空腹血糖：7.8…」要解析出 2 个字段）。

### 7.4 慢病

```
POST /v1/patients/{patient_id}/metrics    body:{name,value,unit?,measured_at?}
GET  /v1/patients/{patient_id}/metrics    query:?name=&limit=   resp: MetricItem[]   ← 新增 GET
GET  /v1/patients/{patient_id}/trend      query:?name=&days=    resp: {name,points:[{t,v}]}  ← 新增，图表用
GET  /v1/patients/{patient_id}/reminders  resp: Reminder[]
GET  /v1/patients                          resp: PatientItem[]   ← 新增列表
POST /v1/patients                          body:{name,age?,gender?}  ← 新增建患者（修 P2-10 外键悬空）
```

### 7.5 工作台（clinician/admin）

```
GET  /v1/workbench/queue                       resp: ReviewItem[]
GET  /v1/workbench/items/{review_id}           resp: ReviewItem
POST /v1/workbench/items/{review_id}/review    body:{decision,corrected_text?}
POST /v1/hitl/resume                           body:{session_id,decision,corrected_text?}
```

`ReviewItem`: `{id, thread_id, session_id, draft, violations, status, created_at, decided_by?, decision?}`

### 7.6 管理后台（admin）

```
GET  /v1/admin/metrics      resp: AdminMetrics
GET  /v1/admin/audit/sessions/{thread_id}
GET  /v1/admin/audit        query:?event=&limit=&offset=   ← 新增全量审计流
GET  /v1/admin/rules        resp: RuleItem[]
PUT  /v1/admin/rules        body:{code,enabled}   ← 必须写审计（P0-5）
GET  /v1/admin/trend        query:?days=  resp:{dates:[],sessions:[],refusals:[],hitls:[]}  ← 新增图表数据
```

`AdminMetrics`: `{total_sessions, total_messages, refusal_rate, safety_rate, hitl_rate, compliance, faithfulness, p95_ms, leak_rate, pending_reviews}`
- `p95_ms` **必须真实计算**（P1-9）
- `leak_rate` **必须真实计算**（P1-10）
- `faithfulness` 保持字段名但改用更严格口径（引用必须含真实 source，非空占位）

### 7.7 药物

```
POST /v1/medication/interactions   body:{drugs:[]}
POST /v1/medication/check          body:{text}
```

---

## 8. 种子数据（`db/seed_demo.py`）

| 用户名 | 密码 | 角色 |
|---|---|---|
| `admin` | `admin123` | admin |
| `doctor` | `doctor123` | clinician |
| `demo` | `demo123` | patient |

同时seed 若干患者 + 纵向指标（供慢病图表直接有数据可看，`patient_id=1`）。

---

## 9. 前端设计契约

- **框架**：React 18 + TS + Vite + Arco Design + Zustand + TanStack Query（**必须真正用起来**，P2-21）
- **主色**：医疗蓝 `#3370FF`；支持亮/暗主题切换（默认跟随 IDE）
- **布局**：飞书式左侧导航 + 顶栏；响应式（<768px 抽屉式）
- **图表**：Recharts —— 慢病趋势折线图、管理后台运营趋势
- **状态**：骨架屏 / 空态 / 错误态 / 加载态四态齐全
- **路由守卫**：未登录跳 `/login`；角色不足跳 403 页
- **禁用**：渐变、emoji（保持项目既定规范）
- **删除**：`src/care_lifeline/api/static/index.html` 及 `app.py` 中的回退逻辑

---

## 10. 质量门禁（必须全绿）

| 门禁 | 要求 |
|---|---|
| `ruff check src tests` | 通过 |
| `ruff format --check src tests` | 通过（本次统一格式化） |
| `mypy src` | 通过 |
| `pytest tests/unit` | 全绿 |
| 全局覆盖率 | ≥ 80% |
| **`src/care_lifeline/safety` 覆盖率** | **= 100%**（在 `pyproject.toml` 真正配置，P1-2） |
| `make eval` 拒答率 | **≥ 90%** |
| 前端 `tsc -b` / `vitest` / `build` | 全绿 |
