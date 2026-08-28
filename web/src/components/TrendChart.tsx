import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTheme } from '@/hooks/useTheme'
import { AsyncState } from './StateBlock'
import { metricValue } from '@/utils/format'

export interface TrendSeries {
  key: string
  name: string
  color?: string
}

export interface TrendChartProps {
  data: Array<Record<string, string | number>>
  xKey?: string
  series: TrendSeries[]
  height?: number
  unit?: string
  /** 参考范围：超出区间的点标红（单条序列时生效，慢病指标用） */
  range?: { min?: number; max?: number }
  loading?: boolean
  error?: unknown
  onRetry?: () => void
}

interface DotRenderProps {
  cx?: number
  cy?: number
  payload?: Record<string, string | number>
}

export default function TrendChart({
  data,
  xKey = 'label',
  series,
  height = 260,
  unit,
  range,
  loading = false,
  error,
  onRetry,
}: TrendChartProps) {
  const { palette } = useTheme()

  const outOfRange = (v: unknown): boolean => {
    if (!range) return false
    const n = Number(v)
    if (Number.isNaN(n)) return false
    if (range.min !== undefined && n < range.min) return true
    if (range.max !== undefined && n > range.max) return true
    return false
  }

  const renderDot = (color: string) => {
    const Dot = (props: DotRenderProps) => {
      const { cx, cy, payload } = props
      if (cx === undefined || cy === undefined) return <g />
      const value = payload?.[series[0]?.key ?? '']
      const abnormal = series.length === 1 && outOfRange(value)
      return (
        <circle
          key={`${cx}-${cy}`}
          cx={cx}
          cy={cy}
          r={abnormal ? 4 : 3}
          fill={abnormal ? palette.danger : color}
          stroke={palette.tooltipBg}
          strokeWidth={1}
        />
      )
    }
    return Dot
  }

  return (
    <AsyncState
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!data.length && !loading && !error}
      skeleton={
        <div className="care-skeleton-bar" style={{ height, borderRadius: 'var(--radius-md)' }} />
      }
      empty={
        <div
          style={{
            height,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-3)',
            fontSize: 13,
          }}
        >
          暂无趋势数据
        </div>
      }
    >
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
            <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 12, fill: palette.axis }}
              stroke={palette.grid}
              tickMargin={8}
            />
            <YAxis
              tick={{ fontSize: 12, fill: palette.axis }}
              stroke={palette.grid}
              width={48}
              tickFormatter={(v: number) => metricValue(v)}
            />
            <Tooltip
              contentStyle={{
                background: palette.tooltipBg,
                border: `1px solid ${palette.tooltipBorder}`,
                borderRadius: 'var(--radius-sm)',
                fontSize: 13,
                boxShadow: 'var(--shadow-pop)',
              }}
              labelStyle={{ color: palette.text, marginBottom: 4 }}
              formatter={(value: number | string, name: string) => [
                `${metricValue(value)}${unit ? ` ${unit}` : ''}`,
                name,
              ]}
            />
            {series.length > 1 && (
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="plainline" />
            )}
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.name}
                stroke={s.color ?? palette.brand}
                strokeWidth={2}
                dot={renderDot(s.color ?? palette.brand)}
                activeDot={{ r: 5, strokeWidth: 0 }}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </AsyncState>
  )
}
