import { http } from './http'
import type {
  AdminMetrics,
  AdminTrend,
  AuditItem,
  AuthUser,
  LoginResponse,
  MessageItem,
  MetricItem,
  PatientItem,
  Reminder,
  ReportResult,
  ReviewDecision,
  ReviewItem,
  Role,
  RuleItem,
  SessionItem,
  TrendResult,
} from '@/types/contract'

/* ------------------------------ 归一化工具 ------------------------------ */

/** 后端列表接口可能返回数组，也可能返回 {items:[]}，统一成数组 */
function asArray<T>(resp: T[] | { items?: T[]; data?: T[] } | null | undefined): T[] {
  if (Array.isArray(resp)) return resp
  if (resp && typeof resp === 'object') {
    const wrapped = (resp as { items?: T[]; data?: T[] }).items
    if (Array.isArray(wrapped)) return wrapped
    const legacy = (resp as { items?: T[]; data?: T[] }).data
    if (Array.isArray(legacy)) return legacy
  }
  return []
}

/** 后端未返回 role（改造过渡期）时按演示账号推断，保证角色路由可用 */
function inferRole(username: string): Role {
  if (username === 'admin') return 'admin'
  if (username === 'doctor') return 'clinician'
  return 'patient'
}

export function normalizeUser(raw: Partial<AuthUser> & { username?: string }): AuthUser {
  const username = raw.username ?? ''
  const role = raw.role ?? inferRole(username)
  return { id: raw.id ?? username, username, role }
}

export function sessionKey(s: Pick<SessionItem, 'session_id' | 'id'>): string {
  return s.session_id ?? String(s.id ?? '')
}

/* -------------------------------- 7.1 鉴权 -------------------------------- */

export const authApi = {
  login: (username: string, password: string) =>
    // 契约：后端同时接受 JSON 与 form，前端按 JSON 发（spec §7.1）
    http.post<LoginResponse>('/auth/login', { username, password }, { silent: true }),
  register: (username: string, password: string, role?: Role) =>
    http.post<LoginResponse>('/auth/register', { username, password, role }, { silent: true }),
  me: () => http.get<AuthUser>('/auth/me', { silent: true }),
}

/* -------------------------------- 7.2 会话 -------------------------------- */

export const sessionApi = {
  list: async () => asArray(await http.get<SessionItem[]>('/sessions', { silent: true })),
  create: (title?: string) => http.post<SessionItem>('/sessions', { title }, { silent: true }),
  remove: (sessionId: string) => http.del<{ ok?: boolean }>(`/sessions/${sessionId}`),
  messages: async (sessionId: string) =>
    asArray(await http.get<MessageItem[]>(`/sessions/${sessionId}/messages`, { silent: true })),
}

/* -------------------------------- 7.3 报告 -------------------------------- */

export const reportApi = {
  interpret: (text: string) =>
    http.post<ReportResult>('/report/interpret', { text }, { silent: true }),
}

/* -------------------------------- 7.4 慢病 -------------------------------- */

export const patientApi = {
  list: async () => asArray(await http.get<PatientItem[]>('/patients', { silent: true })),
  create: (body: { name: string; age?: number; gender?: string }) =>
    http.post<PatientItem>('/patients', body),
  metrics: async (patientId: string | number, name?: string, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) })
    if (name) query.set('name', name)
    return asArray(
      await http.get<MetricItem[]>(`/patients/${patientId}/metrics?${query}`, { silent: true }),
    )
  },
  addMetric: (
    patientId: string | number,
    body: { name: string; value: number; unit?: string; measured_at?: string },
  ) => http.post<MetricItem>(`/patients/${patientId}/metrics`, body),
  trend: (patientId: string | number, name: string, days = 90) =>
    http.get<TrendResult>(`/patients/${patientId}/trend?name=${encodeURIComponent(name)}&days=${days}`, {
      silent: true,
    }),
  reminders: async (patientId: string | number) =>
    asArray(await http.get<Reminder[]>(`/patients/${patientId}/reminders`, { silent: true })),
}

/* ------------------------------ 7.5 医生工作台 ----------------------------- */

export const workbenchApi = {
  queue: async () => asArray(await http.get<ReviewItem[]>('/workbench/queue', { silent: true })),
  item: (reviewId: string | number) =>
    http.get<ReviewItem>(`/workbench/items/${reviewId}`, { silent: true }),
  review: (
    reviewId: string | number,
    decision: ReviewDecision,
    correctedText?: string,
  ) =>
    http.post<{ ok?: boolean }>(`/workbench/items/${reviewId}/review`, {
      decision,
      corrected_text: correctedText,
    }),
  resume: (sessionId: string, decision: ReviewDecision, correctedText?: string) =>
    http.post<{ ok?: boolean }>('/hitl/resume', {
      session_id: sessionId,
      decision,
      corrected_text: correctedText,
    }),
}

/* ------------------------------- 7.6 管理后台 ------------------------------ */

export const adminApi = {
  metrics: () => http.get<AdminMetrics>('/admin/metrics', { silent: true }),
  trend: (days = 14) => http.get<AdminTrend>(`/admin/trend?days=${days}`, { silent: true }),
  audit: async (event?: string, limit = 50, offset = 0) => {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (event) query.set('event', event)
    return asArray(
      await http.get<AuditItem[]>(`/admin/audit?${query}`, { silent: true }),
    )
  },
  auditSession: (threadId: string) =>
    http.get<{ messages?: unknown[]; audit?: AuditItem[] }>(
      `/admin/audit/sessions/${threadId}`,
      { silent: true },
    ),
  rules: async () => asArray(await http.get<RuleItem[]>('/admin/rules', { silent: true })),
  updateRule: (code: string, enabled: boolean) =>
    http.put<{ ok?: boolean }>('/admin/rules', { code, enabled }),
}

/* -------------------------------- 7.7 药物 -------------------------------- */

export const medicationApi = {
  interactions: (drugs: string[]) =>
    http.post<{ warnings?: string[] }>('/medication/interactions', { drugs }, { silent: true }),
  check: (text: string) => http.post<{ warnings?: string[] }>('/medication/check', { text }, { silent: true }),
}
