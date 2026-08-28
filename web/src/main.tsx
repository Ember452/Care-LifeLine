import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from '@arco-design/web-react'
import '@arco-design/web-react/dist/css/arco.css'
import './index.css'
import { router } from './app/router.tsx'
import { useTheme } from './hooks/useTheme'

/**
 * 全局 QueryClient：
 * - 非 SSE 请求统一走 TanStack Query（契约 §9 / P2-21）
 * - 静默 401 由 http.ts 触发登出，路由守卫负责跳转
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})

/** 主题同步：读 Zustand 主题并应用到 DOM（Arco 读 body[arco-theme]，自绘组件读 html[data-theme]） */
function App() {
  useTheme()
  return (
    <ConfigProvider
      theme={{ primaryColor: '#3370FF' }}
      componentConfig={{ Button: { shape: 'round' } }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
