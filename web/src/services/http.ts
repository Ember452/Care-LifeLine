import { Message } from '@arco-design/web-react'
import { useSessionStore } from '@/stores/session'
import type { ApiErrorBody } from '@/types/contract'

export class ApiError extends Error {
  code: string
  status: number
  detail?: unknown

  constructor(code: string, message: string, status = 0, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.detail = detail
  }
}

export interface RequestOptions extends RequestInit {
  baseURL?: string
  token?: string
  /** 静默失败：不弹全局 toast，由页面自己渲染错误态 */
  silent?: boolean
}

/** 把任意后端返回体归一化为 ApiErrorBody（spec §1 统一错误结构） */
function normalizeError(status: number, body: unknown, fallback: string): ApiErrorBody {
  if (body && typeof body === 'object') {
    const raw = body as Record<string, unknown>
    const code = typeof raw.code === 'string' ? raw.code : String(status)
    // 后端旧实现里 detail 可能是裸字符串（已废弃），这里一并兜住
    const message =
      (typeof raw.message === 'string' && raw.message) ||
      (typeof raw.detail === 'string' && raw.detail) ||
      fallback
    return { code, message, detail: raw.detail }
  }
  return { code: String(status), message: fallback }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const base = options.baseURL ?? '/v1'
  const token = options.token ?? useSessionStore.getState().token

  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let res: Response
  try {
    res = await fetch(`${base}${path}`, { ...options, headers })
  } catch {
    // 网络层失败：后端未启动 / 代理不可达 —— 页面据此渲染错误态，不白屏
    const err = new ApiError('network_error', '无法连接服务，请确认后端已启动', 0)
    if (!options.silent) Message.error(err.message)
    throw err
  }

  const text = await res.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (res.status === 401) {
    // 交由路由守卫跳转，不做整页刷新，避免打断 React 状态
    useSessionStore.getState().logout()
    if (!options.silent) Message.error('登录已失效，请重新登录')
    throw new ApiError('unauthorized', '登录已失效，请重新登录', 401)
  }

  if (!res.ok) {
    const normalized = normalizeError(res.status, body, `请求失败 (${res.status})`)
    const err = new ApiError(normalized.code, normalized.message, res.status, normalized.detail)
    if (!options.silent) Message.error(err.message)
    throw err
  }

  return body as T
}

export const http = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}
