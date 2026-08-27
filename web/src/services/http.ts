import { Message } from '@arco-design/web-react'
import { useSessionStore } from '@/stores/session'

export class ApiError extends Error {
  code: string
  detail?: unknown

  constructor(code: string, message: string, detail?: unknown) {
    super(message)
    this.code = code
    this.detail = detail
  }
}

interface RequestOptions extends RequestInit {
  baseURL?: string
  token?: string
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const base = options.baseURL ?? '/v1'
  const token = options.token ?? useSessionStore.getState().token

  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${base}${path}`, { ...options, headers })

  if (res.status === 401) {
    useSessionStore.getState().logout()
    if (typeof window !== 'undefined') window.location.href = '/login'
    throw new ApiError('401', '未授权，请重新登录')
  }

  const text = await res.text()
  const data = text ? JSON.parse(text) : null

  if (!res.ok) {
    const message = data?.message ?? `请求失败 (${res.status})`
    Message.error(message)
    throw new ApiError(String(res.status), message, data?.detail)
  }

  return data as T
}
