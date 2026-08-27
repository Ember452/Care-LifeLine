import { create } from 'zustand'
import type { AuthUser } from '@/types/contract'

interface SessionState {
  token: string | null
  user: AuthUser | null
  setAuth: (token: string, user: AuthUser) => void
  logout: () => void
}

const TOKEN_KEY = 'care_token'

export const useSessionStore = create<SessionState>((set) => ({
  token: typeof localStorage !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null,
  user: null,
  setAuth: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token)
    set({ token, user })
  },
  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    set({ token: null, user: null })
  },
}))
