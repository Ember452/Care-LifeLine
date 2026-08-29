/**
 * 前后端契约类型（唯一依据：docs/superpowers/specs/2026-08-28-full-refactor-contract.md §7）
 *
 * 后端处于并行改造中，字段以"契约为准 + 兼容旧字段名"的方式声明：
 * 后端已实现的字段为必选，契约新增但后端尚未落地的字段一律可选，
 * 前端在 services/ 层做归一化，保证接口不完整时不白屏。
 */

/* ---------------------------------- 通用 ---------------------------------- */

export type Role = 'admin' | 'clinician' | 'patient'

export type RiskLevel = 'routine' | 'urgent' | 'critical'

export type QCStatus = 'passed' | 'warning' | 'hitl' | 'refused'

export type ScopeVerdict = 'in_scope' | 'out_of_scope' | 'restricted' | 'unsafe'

export interface Citation {
  index: number
  source: string
  snippet: string
}

/** 统一错误响应结构（spec §1） */
export interface ApiErrorBody {
  code: string
  message: string
  detail?: unknown
}

/* --------------------------------- 7.1 鉴权 -------------------------------- */

export interface AuthUser {
  id: string | number
  username: string
  role: Role
}

export interface LoginResponse {
  access_token: string
  token_type?: string
  username: string
  role?: Role
}

/* --------------------------------- 7.2 对话 -------------------------------- */

export interface SessionItem {
  /** 会话业务主键（= thread_id），聊天流与消息列表均用它 */
  session_id: string
  /** 兼容旧字段：部分实现返回数据库自增 id */
  id?: string | number
  title?: string | null
  created_at?: string
  updated_at?: string
  message_count?: number
}

export interface MessageItem {
  id?: string | number
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  created_at?: string
}

/* --------------------------------- 7.3 报告 -------------------------------- */

export interface ReportField {
  name: string
  value: string | number
  /** 参考范围，如 "3.5–9.5 ×10⁹/L" */
  reference?: string
  abnormal?: boolean
  unit?: string
}

export interface ReportResult {
  fields: ReportField[]
  citations: Citation[]
  summary?: string
}

/* --------------------------------- 7.4 慢病 -------------------------------- */

export interface PatientItem {
  id: string | number
  name: string
  age?: number | null
  gender?: string | null
}

export interface MetricItem {
  id?: string | number
  name: string
  value: number
  unit?: string | null
  measured_at?: string
}

export interface TrendPoint {
  /** 时间，ISO 字符串或后端自定义短格式 */
  t: string
  v: number
}

export interface TrendResult {
  name: string
  points: TrendPoint[]
}

export interface Reminder {
  patient_id?: string | number
  /** 触发提醒的指标名 */
  metric?: string
  /** 兼容旧字段名 */
  type?: string
  message?: string
  /** 后端 severity 为字符串（info/warning/critical），此处放宽 */
  level?: string
  severity?: string
  created_at?: string
  [key: string]: unknown
}

/* ------------------------------- 7.5 医生工作台 ------------------------------ */

/** 违规项：旧实现为字符串，新契约（spec §2.4）为结构化对象 */
export type QCViolation =
  | string
  | {
      code?: string
      severity?: string
      message?: string
      [key: string]: unknown
    }

export interface ReviewItem {
  id: string | number
  thread_id?: string
  session_id?: string | number
  /** 用户原始提问 */
  input_text?: string
  draft: string
  violations: QCViolation[]
  status: string
  created_at?: string
  decided_by?: string | null
  decision?: string | null
  corrected_text?: string | null
  risk_score?: number
}

export type ReviewDecision = 'approve' | 'reject' | 'revise'

/* ------------------------------- 7.6 管理后台 ------------------------------- */

export interface AdminMetrics {
  total_sessions: number
  total_messages: number
  refusal_rate: number
  safety_rate: number
  hitl_rate: number
  compliance: number
  faithfulness: number
  p95_ms: number
  leak_rate: number
  pending_reviews: number
  /** 兼容旧接口 */
  refuse_rate?: number
}

export interface AdminTrend {
  dates: string[]
  sessions: number[]
  refusals: number[]
  hitls: number[]
}

export interface RuleItem {
  code: string
  name?: string
  description?: string
  enabled: boolean
  severity?: string
}

export interface AuditItem {
  id?: string | number
  event: string
  username?: string
  created_at?: string
  detail?: unknown
  [key: string]: unknown
}

/* ---------------------------------- SSE ---------------------------------- */

export interface SSEMeta {
  session_id: string
  intent: string
  risk_level: RiskLevel
  scope_verdict?: ScopeVerdict
}

export interface SSEToken {
  text: string
}

export interface SSEQC {
  status: QCStatus
  risk_score: number
  violations: QCViolation[]
}

export interface SSETokenUsage {
  input: number
  output: number
  total: number
  /** true = mock 模式字符估算值，非真实计量 */
  estimated?: boolean
}

export interface SSEDone {
  final: string
  citations: Citation[]
  token_usage?: SSETokenUsage | null
}

export interface SSEError {
  code: string
  message: string
}

/** 新增：Agent 节点流转（spec §7.2） */
export interface SSEAgentStep {
  node: string
  detail?: string
}

/** 新增：工具调用（spec §7.2） */
export interface SSEToolCall {
  tool: string
  args_preview?: string
  ok?: boolean
}

/** 新增：患者纵向记忆注入（spec §7.2） */
export interface SSEMemory {
  patient_id?: string | number | null
  metrics_used?: string[]
}

/** hitl 事件：契约为 {reason}，旧实现传的是违规项数组 */
export interface SSEHitl {
  reason?: string | string[]
}

/** 流式质控纠正（可选能力，后端未下发时前端无感） */
export interface SSECorrection {
  message: string
}

export interface SSEEventMap {
  meta: SSEMeta
  token: SSEToken
  citation: Citation
  hitl: SSEHitl
  qc: SSEQC
  correction: SSECorrection
  done: SSEDone
  error: SSEError
  agent_step: SSEAgentStep
  tool_call: SSEToolCall
  memory: SSEMemory
}

export type SSEEventType = keyof SSEEventMap

export interface ChatHandlers {
  onMeta?: (data: SSEMeta) => void
  onToken?: (data: SSEToken) => void
  onCitation?: (data: Citation) => void
  onHitl?: (data: SSEHitl) => void
  onQC?: (data: SSEQC) => void
  onCorrection?: (data: SSECorrection) => void
  onDone?: (data: SSEDone) => void
  onError?: (data: SSEError) => void
  onAgentStep?: (data: SSEAgentStep) => void
  onToolCall?: (data: SSEToolCall) => void
  onMemory?: (data: SSEMemory) => void
  /** 兜底：未识别的事件类型，便于后端新增事件时不丢数据 */
  onUnknown?: (type: string, data: unknown) => void
}
