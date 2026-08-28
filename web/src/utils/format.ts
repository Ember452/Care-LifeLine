import dayjs from 'dayjs'
import type { QCViolation, RiskLevel, Role, ScopeVerdict } from '@/types/contract'

/** 统一提取错误文案：ApiError / Error / 未知值都不该让页面白屏 */
export function errMessage(e: unknown): string {
  if (!e) return '请求失败'
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message || '请求失败'
  if (typeof e === 'object') {
    const raw = e as { message?: unknown; detail?: unknown }
    if (typeof raw.message === 'string' && raw.message) return raw.message
    if (typeof raw.detail === 'string' && raw.detail) return raw.detail
  }
  return '请求失败'
}

export function formatTime(value?: string | number | null): string {
  if (!value) return '—'
  const d = dayjs(value)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : String(value)
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const d = dayjs(value)
  return d.isValid() ? d.format('MM-DD') : String(value)
}

export function percent(value?: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: '管理员',
  clinician: '医生',
  patient: '患者',
}

export const RISK_LABEL: Record<RiskLevel, string> = {
  routine: '常规',
  urgent: '紧急',
  critical: '危急',
}

export const SCOPE_LABEL: Record<ScopeVerdict, string> = {
  in_scope: '服务范围内',
  out_of_scope: '非医疗问题',
  restricted: '越权医疗请求',
  unsafe: '安全风险',
}

export const INTENT_LABEL: Record<string, string> = {
  emergency: '急症识别',
  medication: '用药咨询',
  report: '报告解读',
  triage: '症状分诊',
  refuse: '拒绝回答',
}

export function intentLabel(intent?: string | null): string {
  if (!intent) return '未识别'
  return INTENT_LABEL[intent] ?? intent
}

/** 违规项可能是字符串，也可能是 {code,severity,message} —— 统一成一行文案 */
export function violationText(v: QCViolation): string {
  if (typeof v === 'string') return v
  if (v && typeof v === 'object') {
    return v.message || v.code || JSON.stringify(v)
  }
  return String(v)
}

/** 取违规项编码，用于判断严重级别着色 */
export function violationCode(v: QCViolation): string {
  if (typeof v === 'string') return v
  if (v && typeof v === 'object') return v.code ?? v.message ?? ''
  return String(v)
}

export function metricValue(value: number | string): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return String(value)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}
