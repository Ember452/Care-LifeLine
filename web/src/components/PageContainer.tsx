import type { ReactNode } from 'react'

interface PageContainerProps {
  title: string
  /** 一句说明，不写口号 */
  subtitle?: string
  actions?: ReactNode
  /** 撑满高度且不滚动（对话页用） */
  fill?: boolean
  children: ReactNode
}

export default function PageContainer({
  title,
  subtitle,
  actions,
  fill = false,
  children,
}: PageContainerProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: fill ? '100%' : 'auto',
        minHeight: fill ? 0 : '100%',
        padding: fill ? 0 : 24,
        gap: 16,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: fill ? 'center' : 'flex-end',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
          padding: fill ? '20px 24px 16px' : 0,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: 'var(--text-1)' }}>
            {title}
          </h2>
          {subtitle && (
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-3)' }}>{subtitle}</p>
          )}
        </div>
        {actions && <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{actions}</div>}
      </div>
      <div style={{ flex: fill ? 1 : undefined, minHeight: fill ? 0 : undefined }}>{children}</div>
    </div>
  )
}
