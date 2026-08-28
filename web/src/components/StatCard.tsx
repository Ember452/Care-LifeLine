import type { ReactNode } from 'react'

export type Tone = 'default' | 'brand' | 'success' | 'warning' | 'danger'

const TONE_COLOR: Record<Tone, string> = {
  default: 'var(--text-1)',
  brand: 'var(--brand-500)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

interface StatCardProps {
  label: string
  value: ReactNode
  unit?: string
  hint?: string
  tone?: Tone
  loading?: boolean
}

export default function StatCard({
  label,
  value,
  unit,
  hint,
  tone = 'default',
  loading = false,
}: StatCardProps) {
  return (
    <div className="care-card" style={{ padding: '16px 20px' }}>
      <div style={{ fontSize: 13, color: 'var(--text-3)' }}>{label}</div>
      {loading ? (
        <div className="care-skeleton-bar" style={{ height: 28, marginTop: 10, width: '60%' }} />
      ) : (
        <div
          style={{
            marginTop: 6,
            display: 'flex',
            alignItems: 'baseline',
            gap: 4,
            color: TONE_COLOR[tone],
          }}
        >
          <span
            className="num"
            style={{ fontSize: 26, fontWeight: 600, lineHeight: '34px', letterSpacing: '-0.4px' }}
          >
            {value}
          </span>
          {unit && <span style={{ fontSize: 13, color: 'var(--text-3)' }}>{unit}</span>}
        </div>
      )}
      {hint && (
        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-3)', minHeight: 18 }}>
          {hint}
        </div>
      )}
    </div>
  )
}
