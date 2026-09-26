import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import {
  BarChart2,
  FileText,
  GitCompare,
  LogOut,
  MessageSquare,
  Search,
  ShieldAlert,
  Users,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useFeedStore } from '@/store/feedStore'
import { wsClient } from '@/api/ws'
import type { Permission, WsMessage } from '@/types'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  permission: Permission
}

const navSections: { title?: string; items: NavItem[] }[] = [
  {
    items: [
      { to: '/feed', label: 'Feed', icon: Zap, permission: 'feed:read' },
      { to: '/chat', label: 'Chat', icon: MessageSquare, permission: 'chat:use' },
      { to: '/search', label: 'Search', icon: Search, permission: 'search:read' },
    ],
  },
  {
    title: 'Reliability',
    items: [
      { to: '/risk-board', label: 'Risk Board', icon: ShieldAlert, permission: 'forecast:read' },
      { to: '/reports', label: 'Reports', icon: FileText, permission: 'report:read' },
      { to: '/deployments', label: 'Deployments', icon: GitCompare, permission: 'deployment:read' },
    ],
  },
  {
    title: 'Settings',
    items: [
      { to: '/weights', label: 'Forecast Weights', icon: BarChart2, permission: 'forecast:read' },
      { to: '/users', label: 'Users & Roles', icon: Users, permission: 'user:manage' },
    ],
  },
]

export default function Shell() {
  const logout = useAuthStore((s) => s.logout)
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const can = useAuthStore((s) => s.can)
  const loadUser = useAuthStore((s) => s.loadUser)
  const unreadCount = useFeedStore((s) => s.unreadCount)
  const prependEntry = useFeedStore((s) => s.prependEntry)
  const fetchUnread = useFeedStore((s) => s.fetchUnread)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  // Profile + permissions drive navigation and in-page gating
  useEffect(() => {
    if (token && !user) void loadUser()
  }, [token, user, loadUser])

  // Single WebSocket: route each typed event to the view that owns it
  useEffect(() => {
    if (token) {
      wsClient.connect(token)
      fetchUnread()
    }
    const unsubscribe = wsClient.subscribe((msg: WsMessage) => {
      switch (msg.type) {
        case 'feed_event':
          prependEntry(msg.data)
          break
        case 'alert_event':
          // Proactive alerts interrupt the console (PRD §9.1), wherever the user is
          toast(`${msg.data.service_name}: ${msg.data.risk_tier} failure risk`, { icon: '⚠️' })
          void queryClient.invalidateQueries({ queryKey: ['fleet-health'] })
          void queryClient.invalidateQueries({ queryKey: ['anomalies'] })
          break
      }
    })
    return () => {
      unsubscribe()
    }
  }, [token, prependEntry, fetchUnread, queryClient])

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-52 shrink-0 flex flex-col border-r border-border bg-surface">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-border">
          <span className="font-semibold text-[15px] tracking-tight">LogPilot</span>
          {user && (
            <div className="mt-1 text-xs text-muted truncate" title={user.email}>
              {user.full_name || user.email} · <span className="font-medium">{user.role}</span>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-3 space-y-4 overflow-y-auto">
          {navSections.map(({ title, items }) => {
            const visible = items.filter((item) => can(item.permission))
            if (visible.length === 0) return null
            return (
              <div key={title ?? 'core'} className="space-y-0.5">
                {title && (
                  <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    {title}
                  </div>
                )}
                {visible.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors',
                        isActive
                          ? 'bg-accent/10 text-accent font-medium'
                          : 'text-muted hover:bg-border/60 hover:text-[#1f2328]'
                      )
                    }
                  >
                    <Icon size={16} aria-hidden />
                    <span>{label}</span>
                    {to === '/feed' && unreadCount > 0 && (
                      <span className="ml-auto bg-accent text-white text-[10px] font-semibold px-1.5 py-0.5 rounded-full">
                        {unreadCount > 99 ? '99+' : unreadCount}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>

        {/* Logout */}
        <div className="px-3 py-3 border-t border-border">
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-muted hover:bg-border/60 hover:text-[#1f2328] transition-colors"
          >
            <LogOut size={16} aria-hidden />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
