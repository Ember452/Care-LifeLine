import { Suspense } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from '@/layouts/AppLayout'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import { navItems } from '@/app/nav'

function withSuspense(node: React.ReactNode) {
  return <Suspense fallback={<div style={{ padding: 24, color: 'var(--text-3)' }}>加载中…</div>}>{node}</Suspense>
}

const children = navItems.map((item) => ({
  path: item.path.replace('/', ''),
  element: withSuspense(<item.element />),
}))

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/home" replace /> },
      ...children,
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
