import { useState } from 'react'
import { Tag, Tooltip } from '@arco-design/web-react'
import {
  IconCheckCircleFill,
  IconCloseCircleFill,
  IconLoading,
  IconThunderbolt,
} from '@arco-design/web-react/icon'
import type { ChatMessage } from '@/hooks/useChatStream'
import { SCOPE_LABEL } from '@/utils/format'
import Markdown from './Markdown'
import CitationCard from './CitationCard'

/* --------------------------------------------------------------------------
 * Agent 执行时间线：节点流转 / 工具调用 / 患者记忆 三类步骤竖向排布。
 * 工具调用（真实轨迹）默认展开；节点流转默认折叠，避免淹没正文。
 * -------------------------------------------------------------------------- */

const KIND_META = {
  step: { color: 'var(--brand-500)' },
  tool: { color: 'var(--warning)' },
  memory: { color: 'var(--success)' },
} as const

function StepIcon({ kind, ok }: { kind: string; ok?: boolean }) {
  if (kind === 'tool') {
    return ok === false ? (
      <IconCloseCircleFill style={{ color: 'var(--danger)', fontSize: 14 }} />
    ) : (
      <IconThunderbolt style={{ color: 'var(--warning)', fontSize: 13 }} />
    )
  }
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: KIND_META[kind as keyof typeof KIND_META]?.color ?? 'var(--brand-500)',
        display: 'inline-block',
      }}
    />
  )
}

function AgentTimeline({ message }: { message: ChatMessage }) {
  const steps = message.steps
  const [open, setOpen] = useState(false)
  const toolCount = steps.filter((s) => s.kind === 'tool').length
  if (!steps.length) return null

  return (
    <div className="care-timeline">
      <button type="button" className="care-timeline-toggle" onClick={() => setOpen((o) => !o)}>
        {message.streaming ? (
          <IconLoading spin style={{ color: 'var(--brand-500)', fontSize: 12 }} />
        ) : null}
        <span>
          {toolCount > 0 ? `已调用 ${toolCount} 次工具` : 'Agent 执行过程'}
          <span className="care-timeline-count">· 共 {steps.length} 步</span>
        </span>
        <span className="care-timeline-arrow">{open ? '收起' : '展开'}</span>
      </button>

      {/* 工具调用是真实轨迹：始终展示，让"真 Agent"可见 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>
        {steps
          .filter((s) => s.kind === 'tool')
          .map((s) => (
            <div key={s.id} className="care-timeline-row">
              <StepIcon kind={s.kind} ok={s.ok} />
              <span className="care-timeline-label">
                {s.label}
                {s.detail ? `(${s.detail})` : ''}
              </span>
              <Tooltip content={s.ok === false ? '本次调用失败，模型已改述' : '调用成功'}>
                <Tag size="small" color={s.ok === false ? 'red' : 'green'} style={{ fontSize: 11 }}>
                  {s.ok === false ? '失败' : '成功'}
                </Tag>
              </Tooltip>
            </div>
          ))}
      </div>

      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
          {steps
            .filter((s) => s.kind !== 'tool')
            .map((s) => (
              <div key={s.id} className="care-timeline-row">
                <StepIcon kind={s.kind} />
                <span className="care-timeline-label">
                  {s.label}
                  {s.detail ? <span className="care-timeline-detail"> · {s.detail}</span> : null}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

/* --------------------------------- 提示条 --------------------------------- */

function Notice({ tone, title, children }: {
  tone: 'danger' | 'warning' | 'muted'
  title: string
  children?: React.ReactNode
}) {
  return (
    <div className={`care-notice care-notice-${tone}`}>
      <span className="care-notice-title">{title}</span>
      {children && <div className="care-notice-body">{children}</div>}
    </div>
  )
}

/* ------------------------------- token 脚注 ------------------------------- */

function formatNumber(n: number): string {
  return n.toLocaleString('zh-CN')
}

function TokenFootnote({ usage }: { usage: NonNullable<ChatMessage['tokenUsage']> }) {
  return (
    <Tooltip
      content={`输入 ${usage.input} + 输出 ${usage.output} tokens${usage.estimated ? '（mock 模式为估算值）' : ''}`}
    >
      <span className="care-token-footnote">
        <IconCheckCircleFill style={{ fontSize: 12, marginRight: 4, color: 'var(--success)' }} />
        {formatNumber(usage.total)} tokens
        {usage.estimated ? '（估算）' : ''}
      </span>
    </Tooltip>
  )
}

/* --------------------------------- 主组件 --------------------------------- */

export default function StreamMessage({ message }: { message: ChatMessage }) {
  const [openCitations, setOpenCitations] = useState(false)

  if (message.role === 'user') {
    return (
      <div className="care-msg care-msg-user">
        <div className="care-bubble-user">{message.content}</div>
      </div>
    )
  }

  const qc = message.qc

  return (
    <div className="care-msg">
      {/* scope_verdict：非 in_scope 时展示拒答原因 */}
      {message.scopeVerdict && message.scopeVerdict !== 'in_scope' && (
        <Notice tone="danger" title={`已拒绝 · 该请求被判定为「${SCOPE_LABEL[message.scopeVerdict]}」`}>
          如需医疗建议，请描述具体症状或携带检查报告发起咨询。
        </Notice>
      )}

      {/* hitl 事件：已转人工 */}
      {message.hitl && (
        <Notice tone="warning" title="已转人工医生复核">
          {message.hitl}
        </Notice>
      )}

      {/* qc 状态补充提示 */}
      {qc?.status === 'hitl' && !message.hitl && (
        <Notice tone="warning" title="检测到高风险场景，已转接人工医生复核" />
      )}
      {qc?.status === 'refused' && (
        <Notice tone="muted" title="该请求无法提供回复" />
      )}

      <div className="care-bubble-assistant">
        {message.content ? (
          <Markdown content={message.content} />
        ) : message.streaming ? (
          <div className="care-thinking">
            <span className="care-dot" />
            <span className="care-dot" />
            <span className="care-dot" />
            <span style={{ marginLeft: 8 }}>正在分析…</span>
          </div>
        ) : null}
        {message.streaming && message.content && <span className="care-caret" />}

        <AgentTimeline message={message} />

        {message.error && <div className="care-notice care-notice-danger" style={{ marginTop: 8 }}>{message.error}</div>}

        {message.citations && message.citations.length > 0 && (
          <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {message.citations.map((c) => (
              <Tag
                key={c.index}
                color="arcoblue"
                style={{ cursor: 'pointer', borderRadius: 999 }}
                onClick={() => setOpenCitations((o) => !o)}
              >
                引用 [{c.index}] {c.source}
              </Tag>
            ))}
          </div>
        )}
        {openCitations && message.citations && (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {message.citations.map((c) => (
              <CitationCard key={c.index} citation={c} />
            ))}
          </div>
        )}

        {/* 元信息脚注：质控结论 + token 用量 */}
        {!message.streaming && (qc || message.tokenUsage) && (
          <div className="care-msg-meta">
            {qc && (
              <span>
                质控
                <Tag
                  size="small"
                  style={{ marginLeft: 4, fontSize: 11 }}
                  color={
                    qc.status === 'passed'
                      ? 'green'
                      : qc.status === 'warning'
                        ? 'orange'
                        : qc.status === 'hitl'
                          ? 'orangered'
                          : 'gray'
                  }
                >
                  {qc.status === 'passed'
                    ? '通过'
                    : qc.status === 'warning'
                      ? '提醒'
                      : qc.status === 'hitl'
                        ? '转人工'
                        : '拒答'}
                </Tag>
              </span>
            )}
            {message.tokenUsage && <TokenFootnote usage={message.tokenUsage} />}
          </div>
        )}
      </div>
    </div>
  )
}
