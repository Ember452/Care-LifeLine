import { useState } from 'react'
import { Button, Tag, Typography } from '@arco-design/web-react'
import { IconDown, IconRight } from '@arco-design/web-react/icon'
import type { ChatMessage } from '@/hooks/useChatStream'
import { SCOPE_LABEL } from '@/utils/format'
import Markdown from './Markdown'
import CitationCard from './CitationCard'

const STEP_META: Record<string, { label: string; color: string }> = {
  step: { label: '节点流转', color: 'arcoblue' },
  tool: { label: '工具调用', color: 'purple' },
  memory: { label: '患者记忆', color: 'cyan' },
}

function StepDot({ kind }: { kind: string }) {
  const color = kind === 'tool' ? 'var(--warning)' : kind === 'memory' ? 'var(--success)' : 'var(--brand-500)'
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
        marginTop: 6,
      }}
    />
  )
}

function StepsPanel({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false)
  if (!message.steps.length) return null
  return (
    <div style={{ marginTop: 8 }}>
      <Button size="mini" type="text" onClick={() => setOpen((o) => !o)} style={{ color: 'var(--text-3)', padding: 0 }}>
        {open ? <IconDown /> : <IconRight />}
        <span style={{ marginLeft: 4, fontSize: 12 }}>Agent 处理过程（{message.steps.length} 步）</span>
      </Button>
      {open && (
        <div
          style={{
            marginTop: 6,
            background: 'var(--bg-sunken)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '6px 12px',
            fontSize: 12,
          }}
        >
          {message.steps.map((s) => {
            const m = STEP_META[s.kind] ?? STEP_META.step
            return (
              <div key={s.id} style={{ display: 'flex', gap: 8, padding: '3px 0', alignItems: 'flex-start' }}>
                <StepDot kind={s.kind} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>
                    {m.label}：{s.label}
                  </span>
                  {s.detail && (
                    <span style={{ color: 'var(--text-3)', marginLeft: 8, wordBreak: 'break-all' }}>
                      {s.detail}
                    </span>
                  )}
                  {typeof s.ok === 'boolean' && (
                    <Tag
                      size="small"
                      color={s.ok ? 'green' : 'red'}
                      style={{ marginLeft: 8, fontSize: 11 }}
                    >
                      {s.ok ? '成功' : '失败'}
                    </Tag>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function Notice({ color, bg, border, title, children }: {
  color: string
  bg: string
  border: string
  title: string
  children?: React.ReactNode
}) {
  return (
    <div
      style={{
        background: bg,
        color,
        border,
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 13,
        marginBottom: 8,
      }}
    >
      <Typography.Text bold style={{ color }}>{title}</Typography.Text>
      {children && <div style={{ marginTop: 2 }}>{children}</div>}
    </div>
  )
}

export default function StreamMessage({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false)

  if (message.role === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', margin: '12px 0' }}>
        <div
          style={{
            maxWidth: '70%',
            background: 'var(--brand-100)',
            color: 'var(--text-1)',
            padding: '10px 14px',
            borderRadius: '8px 8px 0 8px',
            whiteSpace: 'pre-wrap',
          }}
        >
          {message.content}
        </div>
      </div>
    )
  }

  const qc = message.qc

  return (
    <div style={{ margin: '12px 0' }}>
      {/* scope_verdict：非 in_scope 时展示拒答原因 */}
      {message.scopeVerdict && message.scopeVerdict !== 'in_scope' && (
        <Notice
          color="var(--danger)"
          bg="var(--danger-bg)"
          border="1px solid var(--danger)"
          title={`已拒绝：该请求被判定为「${SCOPE_LABEL[message.scopeVerdict]}」`}
        >
          如需医疗建议，请描述具体症状或携带检查报告发起咨询。
        </Notice>
      )}

      {/* hitl 事件：已转人工 */}
      {message.hitl && (
        <Notice
          color="var(--warning)"
          bg="var(--warning-bg)"
          border="1px solid var(--warning)"
          title="已转人工医生复核"
        >
          {message.hitl}
        </Notice>
      )}

      {/* qc 状态补充提示 */}
      {qc?.status === 'hitl' && !message.hitl && (
        <Notice
          color="var(--warning)"
          bg="var(--warning-bg)"
          border="1px solid var(--warning)"
          title="检测到高风险场景，已转接人工医生复核"
        />
      )}
      {qc?.status === 'refused' && (
        <Notice
          color="var(--text-3)"
          bg="var(--bg-sunken)"
          border="1px solid var(--border)"
          title="该请求无法提供回复"
        />
      )}

      <div
        style={{
          background: 'var(--bg-card)',
          padding: '12px 16px',
          borderRadius: '8px 8px 8px 0',
          boxShadow: 'var(--shadow-card)',
          border: '1px solid var(--border)',
        }}
      >
        {message.content ? (
          <Markdown content={message.content} />
        ) : message.streaming ? (
          <div style={{ color: 'var(--text-3)', fontSize: 13 }}>正在思考…</div>
        ) : null}
        {message.streaming && (
          <span className="care-caret" style={{ marginTop: 4 }} />
        )}

        {/* Agent 过程透明化面板 */}
        <StepsPanel message={message} />

        {message.error && (
          <div
            style={{
              marginTop: 8,
              color: 'var(--danger)',
              background: 'var(--danger-bg)',
              borderRadius: 6,
              padding: '6px 10px',
              fontSize: 13,
            }}
          >
            {message.error}
          </div>
        )}

        {message.citations && message.citations.length > 0 && (
          <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {message.citations.map((c) => (
              <Tag
                key={c.index}
                color="arcoblue"
                style={{ cursor: 'pointer' }}
                onClick={() => setOpen((o) => !o)}
              >
                [{c.index}] {c.source}
              </Tag>
            ))}
          </div>
        )}
        {open && message.citations && (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {message.citations.map((c) => (
              <CitationCard key={c.index} citation={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
