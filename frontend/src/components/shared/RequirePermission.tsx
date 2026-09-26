import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import type { Permission } from '@/types'

interface Props {
  children: React.ReactNode
  /** If provided, the user must hold this permission (else → /403). */
  permission?: Permission
}

/**
 * Route-level guard. Unauthenticated users → /login.
 * Authenticated but lacking the permission → /403.
 */
export default function RequirePermission({ children, permission }: Props) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)
  const can = useAuthStore((s) => s.can)

  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (permission && !user) {
    return <div className="p-8 text-sm text-muted">Loading…</div>
  }
  if (permission && !can(permission)) return <Navigate to="/403" replace />

  return <>{children}</>
}
