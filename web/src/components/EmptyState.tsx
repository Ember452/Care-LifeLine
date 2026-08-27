import { Button } from '@arco-design/web-react'

export default function EmptyState({ onExample }: { onExample?: () => void }) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-3)',
      }}
    >
      <div style={{ fontSize: 15, marginBottom: 8, color: 'var(--text-2)' }}>
        描述您的症状，开始一次智能问诊
      </div>
      <div style={{ fontSize: 13, marginBottom: 16 }}>示例：最近化验单说贫血，需要注意什么？</div>
      {onExample && (
        <Button type="primary" onClick={onExample}>
          填入示例
        </Button>
      )}
    </div>
  )
}
