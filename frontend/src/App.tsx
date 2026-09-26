import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Shell from '@/components/shared/Shell'
import RequirePermission from '@/components/shared/RequirePermission'
import type { Permission } from '@/types'
import LoginPage from '@/pages/LoginPage'
import FeedPage from '@/pages/FeedPage'
import ChatPage from '@/pages/ChatPage'
import SearchPage from '@/pages/SearchPage'
import RiskBoardPage from '@/pages/RiskBoardPage'
import ReportsPage from '@/pages/ReportsPage'
import ReportDetailPage from '@/pages/ReportDetailPage'
import DeploymentsPage from '@/pages/DeploymentsPage'
import WeightsPage from '@/pages/WeightsPage'
import UsersPage from '@/pages/UsersPage'
import ForbiddenPage from '@/pages/ForbiddenPage'
import NotFoundPage from '@/pages/NotFoundPage'

/** Guarded page; `padded` gives inline-styled screens the gutter they were designed with. */
function page(permission: Permission, element: React.ReactNode, padded = false) {
  return (
    <RequirePermission permission={permission}>
      {padded ? <div className="lp-classic p-8">{element}</div> : element}
    </RequirePermission>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/403" element={<ForbiddenPage />} />
        <Route
          path="/"
          element={
            <RequirePermission>
              <Shell />
            </RequirePermission>
          }
        >
          {/* Default landing = Feed (agent-first per PRD §9.2) */}
          <Route index element={<Navigate to="/feed" replace />} />

          {/* Core agent interface */}
          <Route path="feed" element={page('feed:read', <FeedPage />)} />
          <Route path="chat" element={page('chat:use', <ChatPage />)} />
          <Route path="chat/:sessionId" element={page('chat:use', <ChatPage />)} />
          <Route path="search" element={page('search:read', <SearchPage />)} />

          {/* Reliability */}
          <Route path="risk-board" element={page('forecast:read', <RiskBoardPage />, true)} />
          <Route path="reports" element={page('report:read', <ReportsPage />, true)} />
          <Route path="reports/:id" element={page('report:read', <ReportDetailPage />, true)} />
          <Route path="deployments" element={page('deployment:read', <DeploymentsPage />, true)} />

          {/* Settings */}
          <Route path="weights" element={page('forecast:read', <WeightsPage />, true)} />
          <Route path="users" element={page('user:manage', <UsersPage />, true)} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}
