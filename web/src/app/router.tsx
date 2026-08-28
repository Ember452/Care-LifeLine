import type { ReactNode } from 'react'
import { Suspense } from 'react'
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom'
import AppLayout from '@/layouts/AppLayout'
import LoginPage from '@/pages/LoginPage'
import ForbiddenPage from '@/pages/ForbiddenPage'
import NotFoundPage from '@/pages/NotFoundPage'
import HomePage from '@/pages/HomePage'
import ChatPage from '@/pages/ChatPage'
import ReportPage from '@/pages/ReportPage'
import ChronicPage from '@/pages/ChronicPage'
import WorkbenchPage from '@/pages/WorkbenchPage'
import AdminPage from '@/pages/AdminPage'
import SettingsPage from '@/pages/SettingsPage'
import { useSessionStore } from '@/stores/session'
import type { Role } from '@/types/contract'

function withSuspense(node: ReactNode) {
  return (
    <Suspense
      fallback={
        <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="care-skeleton-bar" style={{ height: 44 }} />
          <div className="care-skeleton-bar" style={{ height: 44 }} />
          <div className="care-skeleton-bar" style={{ height: 44 }} />
        </div>
      }
    >
      {node}
    </Suspense>
  )
}

/** 登录守卫：未登录一律回登录页（http.ts 的 401 也走这里跳转） */
function RequireAuth({ children }: { children: ReactNode }) {
  const token = useSessionStore((s) => s.token)
  const location = useLocation()
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return <>{children}</>
}

/** 角色守卫：角色不足跳 403（契约 §6 RBAC） */
function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const role = useSessionStore((s) => s.role)
  if (!roles.includes(role)) {
    return <Navigate to="/forbidden" replace />
  }
  return <>{children}</>
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/forbidden', element: <ForbiddenPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/home" replace /> },
      { path: 'home', element: withSuspense(<HomePage />) },
      { path: 'chat', element: withSuspense(<ChatPage />) },
      { path: 'report', element: withSuspense(<ReportPage />) },
      { path: 'chronic', element: withSuspense(<ChronicPage />) },
      {
        path: 'workbench',
        element: (
          <RequireRole roles={['clinician', 'admin']}>
            {withSuspense(<WorkbenchPage />)}
          </RequireRole>
        ),
      },
      {
        path: 'admin',
        element: (
          <RequireRole roles={['admin']}>
            {withSuspense(<AdminPage />)}
          </RequireRole>
        ),
      },
      { path: 'settings', element: withSuspense(<SettingsPage />) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
