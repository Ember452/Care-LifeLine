export type RiskLevel = 'routine' | 'urgent' | 'critical'
export type QCStatus = 'passed' | 'hitl' | 'refused'

export interface Citation {
  index: number
  source: string
  snippet: string
}

export interface AuthUser {
  id: string
  username: string
  role: string
}

export interface LoginResponse {
  token: string
  user: AuthUser
}

export interface Session {
  id: string
  thread_id: string
  title: string
  status: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
}

export interface AdminMetrics {
  refuse_rate: number
  leak_rate: number
  faithfulness: number
  compliance: number
  hitl_rate: number
  p95_ms: number
}

export interface SSEMeta {
  session_id: string
  intent: string
  risk_level: RiskLevel
}

export interface SSEQC {
  status: QCStatus
  risk_score: number
  violations: string[]
}

export interface SSEDone {
  final: string
  citations: Citation[]
}

export interface SSEError {
  code: string
  message: string
}

export interface SSEEventMap {
  meta: SSEMeta
  token: { text: string }
  citation: Citation
  qc: SSEQC
  correction: { message: string }
  done: SSEDone
  error: SSEError
}

export type SSEEventType = keyof SSEEventMap

export interface ChatHandlers {
  onMeta?: (data: SSEMeta) => void
  onToken?: (data: { text: string }) => void
  onCitation?: (data: Citation) => void
  onQC?: (data: SSEQC) => void
  onCorrection?: (data: { message: string }) => void
  onDone?: (data: SSEDone) => void
  onError?: (data: SSEError) => void
}
