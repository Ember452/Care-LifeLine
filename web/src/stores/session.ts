import { create } from 'zustand'
import { normalizeUser } from '@/services/api'
import type { AuthUser, Role } from '@/types/contract'

export type ThemeMode = 'light' | 'dark'

const TOKEN_KEY = 'care_token'
const THEME_KEY = 'care_theme'
const USER_KEY = 'care_user'

function readUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? normalizeUser(JSON.parse(raw) as Partial<AuthUser>) : null
  } catch {
    return null
  }
}

function readTheme(): ThemeMode {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'dark' || saved === 'light') return saved
  // 默认跟随系统
  return typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

interface SessionState {
  token: string | null
  user: AuthUser | null
  role: Role
  theme: ThemeMode
  activeSessionId: string | null
  setAuth: (token: string, user: AuthUser) => void
  logout: () => void
  setTheme: (theme: ThemeMode) => void
  setActiveSessionId: (id: string | null) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  token: typeof localStorage !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null,
  user: typeof localStorage !== 'undefined' ? readUser() : null,
  role: (typeof localStorage !== 'undefined' ? readUser()?.role : 'patient') ?? 'patient',
  theme: typeof localStorage !== 'undefined' ? readTheme() : 'light',
  activeSessionId: null,

  setAuth: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    set({ token, user, role: user.role })
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: null, user: null, role: 'patient', activeSessionId: null })
  },

  setTheme: (theme) => {
    localStorage.setItem(THEME_KEY, theme)
    set({ theme })
  },

  setActiveSessionId: (activeSessionId) => set({ activeSessionId }),
}))
