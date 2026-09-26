/**
 * Auth store — JWT token, current user, permissions, login/logout actions.
 *
 * Authorization mirrors the server's permission model (shared.models.Permission):
 * the user's effective permissions come from GET /auth/me, and UI elements are
 * gated with `can(permission)` so they match what the gateway will allow.
 */
import { create } from 'zustand'
import { authApi, setUnauthorizedHandler, tokenStorage } from '@/api'
import { wsClient } from '@/api/ws'
import type { CurrentUser, Permission, Role } from '@/types'

interface AuthState {
  token: string | null
  user: CurrentUser | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  loadUser: () => Promise<void>
  logout: () => void
  can: (permission: Permission) => boolean
  hasRole: (...roles: Role[]) => boolean
}

// Decode a JWT payload without verification (verification happens server-side)
function decodeJwt(token: string): { sub: string; role: Role; exp: number } | null {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(payload))
  } catch {
    return null
  }
}

function storedValidToken(): string | null {
  const token = tokenStorage.get()
  const decoded = token ? decodeJwt(token) : null
  if (token && decoded && decoded.exp * 1000 > Date.now()) return token
  tokenStorage.clear()
  return null
}

const initialToken = storedValidToken()

export const useAuthStore = create<AuthState>()((set, get) => ({
  token: initialToken,
  user: null,
  isAuthenticated: initialToken !== null,

  login: async (email, password) => {
    const resp = await authApi.login(email, password)
    tokenStorage.set(resp.access_token)
    set({ token: resp.access_token, isAuthenticated: true })
    await get().loadUser()
  },

  loadUser: async () => {
    try {
      set({ user: await authApi.me() })
    } catch {
      // 401s are handled by the unauthorized handler below
    }
  },

  logout: () => {
    tokenStorage.clear()
    wsClient.disconnect()
    set({ token: null, user: null, isAuthenticated: false })
  },

  can: (permission) => get().user?.permissions.includes(permission) ?? false,

  hasRole: (...roles) => {
    const role = get().user?.role
    return !!role && roles.includes(role)
  },
}))

// Any 401 from the API means the session is no longer valid
setUnauthorizedHandler(() => {
  if (useAuthStore.getState().isAuthenticated) {
    useAuthStore.getState().logout()
  }
})
