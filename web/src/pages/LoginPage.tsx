import { useState } from 'react'
import { Alert, Button, Input, Space, Typography } from '@arco-design/web-react'
import { useMutation } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { authApi, normalizeUser } from '@/services/api'
import { useSessionStore } from '@/stores/session'
import { errMessage } from '@/utils/format'
import type { Role } from '@/types/contract'

interface DemoAccount {
  username: string
  password: string
  label: string
  role: Role
}

const DEMO_ACCOUNTS: DemoAccount[] = [
  { username: 'admin', password: 'admin123', label: '管理员', role: 'admin' },
  { username: 'doctor', password: 'doctor123', label: '医生', role: 'clinician' },
  { username: 'demo', password: 'demo123', label: '患者', role: 'patient' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const token = useSessionStore((s) => s.token)
  const setAuth = useSessionStore((s) => s.setAuth)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const login = useMutation({
    mutationFn: () => authApi.login(username.trim(), password),
    onSuccess: (resp) => {
      const user = normalizeUser({ username: resp.username, role: resp.role })
      setAuth(resp.access_token, user)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from !== '/login' ? from : '/chat', { replace: true })
    },
  })

  // 已登录直接进主界面
  if (token) return <Navigate to="/chat" replace />

  const fill = (acc: DemoAccount) => {
    setUsername(acc.username)
    setPassword(acc.password)
    login.mutate()
  }

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-page)',
        padding: 16,
      }}
    >
      <div
        style={{
          width: 400,
          maxWidth: '100%',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-pop)',
          padding: '32px 32px 24px',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 8 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--brand-500)', letterSpacing: 0.2 }}>
            Care-LifeLine
          </div>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            智能诊疗辅助平台
          </Typography.Text>
        </div>

        {login.isError && (
          <Alert
            type="error"
            closable
            style={{ marginBottom: 16 }}
            content={errMessage(login.error) || '登录失败，请检查账号密码'}
          />
        )}

        <Space direction="vertical" size={12} style={{ width: '100%', marginBottom: 20 }}>
          <Input
            placeholder="用户名"
            value={username}
            onChange={setUsername}
            autoComplete="username"
            onPressEnter={() => login.mutate()}
          />
          <Input.Password
            placeholder="密码"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            onPressEnter={() => login.mutate()}
          />
          <Button
            long
            type="primary"
            loading={login.isPending}
            disabled={!username.trim() || !password}
            onClick={() => login.mutate()}
          >
            登录
          </Button>
        </Space>

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>演示账号一键登录</div>
          <Space size={8} wrap>
            {DEMO_ACCOUNTS.map((acc) => (
              <Button
                key={acc.username}
                size="small"
                type="outline"
                loading={login.isPending}
                onClick={() => fill(acc)}
              >
                {acc.label} · {acc.username}
              </Button>
            ))}
          </Space>
        </div>
      </div>
    </div>
  )
}
