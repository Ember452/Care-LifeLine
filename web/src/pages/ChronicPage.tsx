import { useEffect, useState } from 'react'
import { Button, Input, InputNumber, Message, Select, Space, Tag } from '@arco-design/web-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { patientApi } from '@/services/api'
import PageContainer from '@/components/PageContainer'
import TrendChart from '@/components/TrendChart'
import { AsyncState } from '@/components/StateBlock'
import { formatDate, formatTime, metricValue } from '@/utils/format'
import type { Reminder } from '@/types/contract'

interface MetricOption {
  name: string
  unit: string
  range: { min?: number; max?: number }
}

const METRIC_OPTIONS: MetricOption[] = [
  { name: '收缩压', unit: 'mmHg', range: { min: 90, max: 139 } },
  { name: '舒张压', unit: 'mmHg', range: { min: 60, max: 89 } },
  { name: '空腹血糖', unit: 'mmol/L', range: { min: 3.9, max: 6.1 } },
  { name: '糖化血红蛋白', unit: '%', range: { min: 4, max: 6 } },
  { name: '心率', unit: '次/分', range: { min: 60, max: 100 } },
]

const REMINDER_COLOR: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
  info: 'arcoblue',
}

function severityOf(r: Reminder): string {
  return String(r.severity ?? r.level ?? 'info')
}

export default function ChronicPage() {
  const queryClient = useQueryClient()
  const [patientId, setPatientId] = useState<number | null>(null)
  const [metricName, setMetricName] = useState<string>(METRIC_OPTIONS[0].name)
  const [value, setValue] = useState<number | undefined>(undefined)
  const [unit, setUnit] = useState<string>(METRIC_OPTIONS[0].unit)

  /* ------------------------------ 患者列表 ------------------------------ */
  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: patientApi.list,
    staleTime: 30_000,
  })

  useEffect(() => {
    if (patientId === null && patientsQuery.data && patientsQuery.data.length > 0) {
      setPatientId(Number(patientsQuery.data[0].id))
    }
  }, [patientsQuery.data, patientId])

  /* ------------------------------ 趋势图 ------------------------------ */
  const trendQuery = useQuery({
    queryKey: ['trend', patientId, metricName],
    queryFn: () => patientApi.trend(patientId as number, metricName, 90),
    enabled: patientId !== null,
  })

  const trendData = (trendQuery.data?.points ?? []).map((p) => ({
    label: formatDate(p.t),
    v: Number(p.v),
  }))
  const activeMetric = METRIC_OPTIONS.find((m) => m.name === metricName)

  /* ------------------------------ 指标录入 ------------------------------ */
  const addMetric = useMutation({
    mutationFn: () =>
      patientApi.addMetric(patientId as number, {
        name: metricName,
        value: value as number,
        unit,
      }),
    onSuccess: () => {
      Message.success('指标已记录')
      setValue(undefined)
      void queryClient.invalidateQueries({ queryKey: ['trend', patientId] })
      void queryClient.invalidateQueries({ queryKey: ['reminders', patientId] })
    },
  })

  /* ------------------------------ 主动提醒 ------------------------------ */
  const remindersQuery = useQuery({
    queryKey: ['reminders', patientId],
    queryFn: () => patientApi.reminders(patientId as number),
    enabled: patientId !== null,
  })

  return (
    <PageContainer title="慢病管理" subtitle="记录慢病指标，跟踪趋势变化并接收主动提醒">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 360px) 1fr', gap: 16, alignItems: 'start' }}>
        {/* 左：患者选择 + 指标录入 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="care-card" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 8 }}>选择患者</div>
            <AsyncState
              loading={patientsQuery.isLoading}
              error={patientsQuery.error}
              onRetry={() => void queryClient.invalidateQueries({ queryKey: ['patients'] })}
              isEmpty={(patientsQuery.data ?? []).length === 0}
              empty={<div style={{ padding: 12, color: 'var(--text-3)', fontSize: 13 }}>暂无患者数据</div>}
              skeleton={<div className="care-skeleton-bar" style={{ height: 36 }} />}
            >
              <Select
                value={patientId ?? undefined}
                placeholder="选择患者"
                style={{ width: '100%' }}
                onChange={(v) => setPatientId(Number(v))}
              >
                {(patientsQuery.data ?? []).map((p) => (
                  <Select.Option key={p.id} value={p.id}>
                    {p.name}
                    {p.age ? ` · ${p.age}岁` : ''}
                  </Select.Option>
                ))}
              </Select>
            </AsyncState>
          </div>

          <div className="care-card" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 12 }}>录入指标</div>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Select
                value={metricName}
                onChange={(v) => {
                  const m = METRIC_OPTIONS.find((o) => o.name === v)
                  setMetricName(v)
                  setUnit(m?.unit ?? '')
                }}
                style={{ width: '100%' }}
              >
                {METRIC_OPTIONS.map((m) => (
                  <Select.Option key={m.name} value={m.name}>
                    {m.name}（{m.unit}）
                  </Select.Option>
                ))}
              </Select>
              <Space size={8}>
                <InputNumber
                  placeholder="测量值"
                  value={value}
                  onChange={setValue}
                  style={{ flex: 1 }}
                  min={0}
                />
                <Input
                  placeholder="单位"
                  value={unit}
                  onChange={setUnit}
                  style={{ width: 96 }}
                  maxLength={12}
                />
              </Space>
              <Button
                long
                type="primary"
                disabled={!patientId || value === undefined || Number.isNaN(Number(value))}
                loading={addMetric.isPending}
                onClick={() => addMetric.mutate()}
              >
                保存指标
              </Button>
            </Space>
          </div>
        </div>

        {/* 右：趋势图 + 提醒 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="care-card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>近 90 天趋势</div>
              <Tag color="arcoblue">{metricName}</Tag>
            </div>
            <TrendChart
              data={trendData}
              xKey="label"
              series={[{ key: 'v', name: metricName, color: 'var(--brand-500)' }]}
              unit={unit || activeMetric?.unit}
              range={activeMetric?.range}
              height={280}
              loading={trendQuery.isLoading}
              error={trendQuery.error}
              onRetry={() => void queryClient.invalidateQueries({ queryKey: ['trend', patientId] })}
            />
            {trendData.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>
                最近一次：{metricValue(trendData[trendData.length - 1].v)}
                {unit || activeMetric?.unit ? ` ${unit || activeMetric?.unit}` : ''}
                {activeMetric?.range?.min !== undefined && activeMetric?.range?.max !== undefined
                  ? `（参考范围 ${activeMetric.range.min}–${activeMetric.range.max}）`
                  : ''}
              </div>
            )}
          </div>

          <div className="care-card" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 8 }}>主动提醒</div>
            <AsyncState
              loading={remindersQuery.isLoading}
              error={remindersQuery.error}
              onRetry={() => void queryClient.invalidateQueries({ queryKey: ['reminders', patientId] })}
              isEmpty={(remindersQuery.data ?? []).length === 0}
              empty={<div style={{ padding: 12, color: 'var(--text-3)', fontSize: 13 }}>暂无提醒</div>}
            >
              {(remindersQuery.data ?? []).map((r, i) => {
                const sev = severityOf(r)
                return (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 10,
                      padding: '10px 4px',
                      borderBottom: '1px solid var(--border)',
                      fontSize: 13,
                    }}
                  >
                    <Tag color={REMINDER_COLOR[sev] ?? 'arcoblue'} size="small" style={{ marginTop: 1 }}>
                      {sev === 'critical' ? '危急' : sev === 'warning' ? '关注' : '提醒'}
                    </Tag>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: 'var(--text-1)' }}>
                        {r.metric ? `${r.metric}：` : ''}
                        {r.message || JSON.stringify(r)}
                      </div>
                      {r.created_at && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{formatTime(r.created_at)}</div>}
                    </div>
                  </div>
                )
              })}
            </AsyncState>
          </div>
        </div>
      </div>
    </PageContainer>
  )
}
