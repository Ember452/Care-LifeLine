import { request } from './http'
import type { AuthUser, LoginResponse, Session } from '@/types/contract'

export const authApi = {
  login: (username: string, password: string) =>
    request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<AuthUser>('/auth/me'),
}

export const sessionApi = {
  list: () => request<Session[]>('/sessions'),
  create: (title?: string) =>
    request<Session>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
}
