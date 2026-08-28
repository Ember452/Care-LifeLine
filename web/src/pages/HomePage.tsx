import { Button, Tag } from '@arco-design/web-react'
import { useNavigate } from 'react-router-dom'
import { navItemsForRole } from '@/app/nav'
import PageContainer from '@/components/PageContainer'
import { useSessionStore } from '@/stores/session'
import { ROLE_LABEL } from '@/utils/format'

const MODULE_DESC: Record<string, string> = {
  chat: '流式智能问诊，Agent 过程透明可视',
  report: '检验报告文本结构化解读与异常标注',
  chronic: '慢病指标录入、趋势跟踪与主动提醒',
  workbench: '复核 AI 回复，通过 / 驳回 / 修正',
  admin: '运营指标、审计流水与质控规则',
  settings: '主题与账号设置',
}

export default function HomePage() {
  const navigate = useNavigate()
  const user = useSessionStore((s) => s.user)
  const role = useSessionStore((s) => s.role)
  const nav = navItemsForRole(role).filter((n) => n.key !== 'home')

  return (
    <PageContainer title={`你好，${user?.username ?? '用户'}`} subtitle={`当前身份：${ROLE_LABEL[role]} · 选择功能模块开始工作`}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
        {nav.map((item) => (
          <div
            key={item.key}
            className="care-card"
            style={{ padding: 20, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }}
            onClick={() => navigate(item.path)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 8,
                  background: 'var(--brand-100)',
                  color: 'var(--brand-500)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <item.icon />
              </div>
              <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-1)' }}>{item.label}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-3)', lineHeight: 1.6, minHeight: 40 }}>
              {MODULE_DESC[item.key] ?? ''}
            </div>
            <div>
              <Button size="small" type="text">
                进入
              </Button>
            </div>
          </div>
        ))}
      </div>

      <div className="care-card" style={{ marginTop: 16, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <Tag color="arcoblue">医疗安全提示</Tag>
        <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
          所有 AI 回复均经质控审核，高危场景自动转人工复核；紧急情况请立即拨打急救电话。
        </span>
      </div>
    </PageContainer>
  )
}
