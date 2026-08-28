import { useMemo, useState } from 'react'
import { Message, Select, Switch, Tag } from '@arco-design/web-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '@/services/api'
import PageContainer from '@/components/PageContainer'
import StatCard from '@/components/StatCard'
import TrendChart from '@/components/TrendChart'
import { AsyncState } from '@/components/StateBlock'
import { formatTime, percent } from '@/utils/format'
import type { AuditItem } from '@/types/contract'

const AUDIT_EVENTS = [
  'chat_completed',
  'hitl_review_created',
  'hitl_review_approve',
  'hitl_review_reject',
  'hitl_review_edit',
  'hitl_review_revise',
  'qc_rule_toggled',
  'phi_leak',
]

const EVENT_LABEL: Record<string, string> = {
  chat_completed: '对话完成',
  hitl_review_created: '创建审核',
  hitl_review_approve: '审核通过',
  hitl_review_reject: '审核驳回',
  hitl_review_edit: '审核修正',
  hitl_review_revise: '审核修订',
  qc_rule_toggled: '规则启停',
  phi_leak: '隐私泄漏',
}

function eventLabel(e: string): string {
  return EVENT_LABEL[e] ?? e
}

function eventColor(e: string): string {
  if (e === 'phi_leak') return 'red'
  if (e.startsWith('hitl_review')) return 'orange'
  if (e === 'qc_rule_toggled') return 'purple'
  return 'arcoblue'
}

export default function AdminPage() {
  const queryClient = useQueryClient()
  const [days, setDays] = useState(14)
  const [eventFilter, setEventFilter] = useState<string | undefined>(undefined)

  /* ------------------------------ 指标 ------------------------------ */
  const metricsQuery = useQuery({
    queryKey: ['admin-metrics'],
    queryFn: adminApi.metrics,
    refetchInterval: 30_000,
  })
  const m = metricsQuery.data

  /* ------------------------------ 运营趋势 ------------------------------ */
  const trendQuery = useQuery({
    queryKey: ['admin-trend', days],
    queryFn: () => adminApi.trend(days),
  })
  const trendData = useMemo(
    () =>
      (trendQuery.data?.dates ?? []).map((d, i) => ({
        label: d.slice(5),
        sessions: trendQuery.data?.sessions?.[i] ?? 0,
        refusals: trendQuery.data?.refusals?.[i] ?? 0,
        hitls: trendQuery.data?.hitls?.[i] ?? 0,
      })),
    [trendQuery.data],
  )

  /* ------------------------------ 审计流水 ------------------------------ */
  const auditQuery = useQuery({
    queryKey: ['admin-audit', eventFilter],
    queryFn: () => adminApi.audit(eventFilter, 50, 0),
  })

  /* ------------------------------ 质控规则 ------------------------------ */
  const rulesQuery = useQuery({
    queryKey: ['admin-rules'],
    queryFn: adminApi.rules,
  })

  const toggleRule = useMutation({
    mutationFn: ({ code, enabled }: { code: string; enabled: boolean }) =>
      adminApi.updateRule(code, enabled),
    onSuccess: () => {
      Message.success('规则状态已更新')
      void queryClient.invalidateQueries({ queryKey: ['admin-rules'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audit'] })
    },
    onError: (e) => {
      Message.error(e instanceof Error ? e.message : '更新失败')
      void queryClient.invalidateQueries({ queryKey: ['admin-rules'] })
    },
  })

  const ruleList = rulesQuery.data ?? []

  return (
    <PageContainer title="管理后台" subtitle="平台运营指标与质控规则配置（仅管理员可见）">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* 指标卡片组 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <StatCard label="会话总数" value={m?.total_sessions ?? '—'} loading={metricsQuery.isLoading} />
          <StatCard label="消息总数" value={m?.total_messages ?? '—'} loading={metricsQuery.isLoading} />
          <StatCard
            label="拒答率"
            value={m ? percent(m.refusal_rate) : '—'}
            tone="danger"
            loading={metricsQuery.isLoading}
            hint="非医疗 / 越权请求占比"
          />
          <StatCard
            label="转人工率"
            value={m ? percent(m.hitl_rate) : '—'}
            tone="warning"
            loading={metricsQuery.isLoading}
            hint="高风险介入占比"
          />
          <StatCard
            label="合规率"
            value={m ? percent(m.compliance) : '—'}
            tone="success"
            loading={metricsQuery.isLoading}
            hint="通过质控的回复占比"
          />
          <StatCard
            label="P95 延迟"
            value={m?.p95_ms != null ? Math.round(m.p95_ms) : '—'}
            unit="ms"
            loading={metricsQuery.isLoading}
            hint="95 分位响应延迟"
          />
          <StatCard
            label="泄漏率"
            value={m ? percent(m.leak_rate) : '—'}
            tone="danger"
            loading={metricsQuery.isLoading}
            hint="隐私信息泄漏占比"
          />
          <StatCard
            label="待审事项"
            value={m?.pending_reviews ?? '—'}
            tone="default"
            loading={metricsQuery.isLoading}
            hint="工作台待处理数"
          />
        </div>

        {/* 运营趋势 */}
        <div className="care-card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>运营趋势</span>
            <Select
              size="small"
              value={days}
              onChange={(v) => setDays(Number(v))}
              style={{ width: 120 }}
            >
              <Select.Option value={7}>近 7 天</Select.Option>
              <Select.Option value={14}>近 14 天</Select.Option>
              <Select.Option value={30}>近 30 天</Select.Option>
            </Select>
          </div>
          <TrendChart
            data={trendData}
            xKey="label"
            height={280}
            series={[
              { key: 'sessions', name: '会话数', color: 'var(--brand-500)' },
              { key: 'refusals', name: '拒答数', color: 'var(--danger)' },
              { key: 'hitls', name: '转人工数', color: 'var(--warning)' },
            ]}
            loading={trendQuery.isLoading}
            error={trendQuery.error}
            onRetry={() => void queryClient.invalidateQueries({ queryKey: ['admin-trend', days] })}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
          {/* 质控规则 */}
          <div className="care-card" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 8 }}>质控规则启停</div>
            <AsyncState
              loading={rulesQuery.isLoading}
              error={rulesQuery.error}
              onRetry={() => void queryClient.invalidateQueries({ queryKey: ['admin-rules'] })}
              isEmpty={ruleList.length === 0}
            >
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {ruleList.map((r) => (
                  <div
                    key={r.code}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      padding: '10px 4px',
                      borderBottom: '1px solid var(--border)',
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 14, color: 'var(--text-1)', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="num" style={{ fontSize: 12, color: 'var(--brand-500)' }}>{r.code}</span>
                        {r.severity && (
                          <Tag size="small" color={String(r.severity).toLowerCase() === 'blocking' ? 'red' : 'orange'}>
                            {String(r.severity).toLowerCase() === 'blocking' ? '阻断' : '警告'}
                          </Tag>
                        )}
                      </div>
                      {r.description && (
                        <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{r.description}</div>
                      )}
                    </div>
                    <Switch
                      size="small"
                      checked={r.enabled}
                      loading={toggleRule.isPending}
                      onChange={(checked) => toggleRule.mutate({ code: r.code, enabled: checked })}
                    />
                  </div>
                ))}
              </div>
            </AsyncState>
          </div>

          {/* 审计流水 */}
          <div className="care-card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-3)' }}>审计流水</span>
              <Select
                size="small"
                allowClear
                placeholder="全部事件"
                value={eventFilter}
                onChange={(v) => setEventFilter(v || undefined)}
                style={{ width: 160 }}
              >
                {AUDIT_EVENTS.map((e) => (
                  <Select.Option key={e} value={e}>
                    {eventLabel(e)}
                  </Select.Option>
                ))}
              </Select>
            </div>
            <AsyncState
              loading={auditQuery.isLoading}
              error={auditQuery.error}
              onRetry={() => void queryClient.invalidateQueries({ queryKey: ['admin-audit', eventFilter] })}
              isEmpty={(auditQuery.data ?? []).length === 0}
              empty={<div style={{ padding: 12, color: 'var(--text-3)', fontSize: 13 }}>暂无审计记录</div>}
            >
              <div className="care-scroll" style={{ maxHeight: 420, overflowY: 'auto' }}>
                {(auditQuery.data ?? []).map((row) => (
                  <AuditRow key={row.id ?? `${row.event}-${row.created_at}`} row={row} />
                ))}
              </div>
            </AsyncState>
          </div>
        </div>
      </div>
    </PageContainer>
  )
}

function AuditRow({ row }: { row: AuditItem }) {
  const detail = typeof row.detail === 'string' ? row.detail : row.detail != null ? JSON.stringify(row.detail) : ''
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '8px 4px',
        borderBottom: '1px solid var(--border)',
        fontSize: 13,
      }}
    >
      <Tag color={eventColor(row.event)} size="small" style={{ flexShrink: 0, marginTop: 1 }}>
        {eventLabel(row.event)}
      </Tag>
      <div style={{ minWidth: 0, flex: 1 }}>
        {detail && (
          <div
            style={{ color: 'var(--text-2)', wordBreak: 'break-all', fontSize: 12 }}
            title={detail}
          >
            {detail}
          </div>
        )}
        <div style={{ color: 'var(--text-3)', fontSize: 12, marginTop: 2 }}>
          {formatTime(row.created_at)}
          {row.session_id != null ? ` · 会话 #${row.session_id}` : ''}
        </div>
      </div>
    </div>
  )
}
