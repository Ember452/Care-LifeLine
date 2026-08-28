import { Message, Radio } from '@arco-design/web-react'
import { IconMoonFill, IconSunFill } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { authApi } from '@/services/api'
import PageContainer from '@/components/PageContainer'
import { AsyncState } from '@/components/StateBlock'
import { useSessionStore } from '@/stores/session'
import { ROLE_LABEL } from '@/utils/format'

export default function SettingsPage() {
  const theme = useSessionStore((s) => s.theme)
  const setTheme = useSessionStore((s) => s.setTheme)
  const localUser = useSessionStore((s) => s.user)

  const meQuery = useQuery({
    queryKey: ['auth-me'],
    queryFn: authApi.me,
    staleTime: 60_000,
  })
  const me = meQuery.data

  return (
    <PageContainer title="设置" subtitle="外观与账号信息">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 640 }}>
        {/* 主题 */}
        <div className="care-card" style={{ padding: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 12 }}>外观主题</div>
          <Radio.Group
            type="button"
            value={theme}
            onChange={(v) => {
              setTheme(v as 'light' | 'dark')
              Message.success(v === 'dark' ? '已切换为暗色主题' : '已切换为亮色主题')
            }}
          >
            <Radio value="light">
              <IconSunFill style={{ marginRight: 4 }} />
              亮色
            </Radio>
            <Radio value="dark">
              <IconMoonFill style={{ marginRight: 4 }} />
              暗色
            </Radio>
          </Radio.Group>
        </div>

        {/* 账号信息 */}
        <div className="care-card" style={{ padding: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 12 }}>账号信息</div>
          <AsyncState
            loading={meQuery.isLoading}
            error={meQuery.error}
            onRetry={() => meQuery.refetch()}
            skeleton={
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div className="care-skeleton-bar" style={{ height: 28 }} />
                <div className="care-skeleton-bar" style={{ height: 28 }} />
              </div>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 14 }}>
              <div style={{ display: 'flex', gap: 12 }}>
                <span style={{ color: 'var(--text-3)', width: 80 }}>用户名</span>
                <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>{me?.username ?? localUser?.username ?? '—'}</span>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <span style={{ color: 'var(--text-3)', width: 80 }}>角色</span>
                <span style={{ color: 'var(--text-1)' }}>
                  {me?.role ? `${ROLE_LABEL[me.role]}（${me.role}）` : ROLE_LABEL[localUser?.role ?? 'patient']}
                </span>
              </div>
              {me?.id != null && (
                <div style={{ display: 'flex', gap: 12 }}>
                  <span style={{ color: 'var(--text-3)', width: 80 }}>用户 ID</span>
                  <span className="num" style={{ color: 'var(--text-1)' }}>{me.id}</span>
                </div>
              )}
            </div>
          </AsyncState>
        </div>

        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
          Care-LifeLine 智能诊疗辅助平台 · 演示环境
        </div>
      </div>
    </PageContainer>
  )
}
