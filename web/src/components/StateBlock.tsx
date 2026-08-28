import type { ReactNode } from 'react'
import { Button, Empty } from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import { errMessage } from '@/utils/format'

/** 骨架屏：加载态优先于转圈 */
export function LoadingSkeleton({ rows = 3, height = 44 }: { rows?: number; height?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 4 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="care-skeleton-bar" style={{ height }} />
      ))}
    </div>
  )
}

export function EmptyBlock({
  title = '暂无数据',
  description,
  action,
}: {
  title?: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div style={{ padding: '32px 0', display: 'flex', justifyContent: 'center' }}>
      <Empty
        description={
          <div>
            <div style={{ color: 'var(--text-2)' }}>{title}</div>
            {description && (
              <div style={{ color: 'var(--text-3)', fontSize: 13, marginTop: 4 }}>{description}</div>
            )}
            {action && <div style={{ marginTop: 12 }}>{action}</div>}
          </div>
        }
      />
    </div>
  )
}

export function ErrorBlock({
  error,
  onRetry,
  compact = false,
}: {
  error: unknown
  onRetry?: () => void
  compact?: boolean
}) {
  return (
    <div
      style={{
        padding: compact ? 16 : 32,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 14, color: 'var(--text-1)', fontWeight: 600 }}>数据加载失败</div>
      <div style={{ fontSize: 13, color: 'var(--text-3)', maxWidth: 420, lineHeight: 1.6 }}>
        {errMessage(error)}
      </div>
      {onRetry && (
        <Button type="primary" icon={<IconRefresh />} onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  )
}

/**
 * 四态容器：骨架屏 / 空态 / 错误态 / 内容。
 * 所有异步区块统一走这里，保证每个页面四态齐全且不遗漏。
 */
export function AsyncState({
  loading,
  error,
  isEmpty = false,
  onRetry,
  skeleton,
  empty,
  children,
}: {
  loading: boolean
  error?: unknown
  isEmpty?: boolean
  onRetry?: () => void
  skeleton?: ReactNode
  empty?: ReactNode
  children: ReactNode
}) {
  if (loading) return <>{skeleton ?? <LoadingSkeleton />}</>
  if (error) return <ErrorBlock error={error} onRetry={onRetry} />
  if (isEmpty) return <>{empty ?? <EmptyBlock />}</>
  return <>{children}</>
}
