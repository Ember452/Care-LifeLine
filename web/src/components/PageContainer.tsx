import type { ReactNode } from 'react'
import { Card } from '@arco-design/web-react'

interface PageContainerProps {
  title: string
  children?: ReactNode
}

export default function PageContainer({ title, children }: PageContainerProps) {
  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: 'var(--text-1)' }}>{title}</h2>
      <Card bordered={false} style={{ boxShadow: 'var(--shadow-card)' }}>
        {children ?? <span style={{ color: 'var(--text-3)' }}>模块建设中</span>}
      </Card>
    </div>
  )
}
