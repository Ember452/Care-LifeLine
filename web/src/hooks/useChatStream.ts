import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '@/services/chat'
import { useSessionStore } from '@/stores/session'
import type {
  ChatHandlers,
  Citation,
  MessageItem,
  RiskLevel,
  ScopeVerdict,
  SSEQC,
} from '@/types/contract'

export type AgentStepKind = 'step' | 'tool' | 'memory'

export interface AgentStepItem {
  id: string
  kind: AgentStepKind
  label: string
  detail?: string
  ok?: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  qc?: SSEQC
  /** hitl 事件：转人工原因 */
  hitl?: string
  /** scope_verdict：非 in_scope 时展示拒答原因 */
  scopeVerdict?: ScopeVerdict
  /** Agent 执行过程（agent_step / tool_call / memory） */
  steps: AgentStepItem[]
  streaming?: boolean
  error?: string
}

let seq = 0
function uid(): string {
  seq += 1
  return `${Date.now()}-${seq}`
}

function fromHistoryItem(m: MessageItem): ChatMessage {
  return {
    id: String(m.id ?? uid()),
    role: m.role === 'assistant' ? 'assistant' : 'user',
    content: m.content ?? '',
    citations: m.citations?.length ? m.citations : undefined,
    steps: [],
  }
}

export interface UseChatStreamOptions {
  /** 服务端历史消息，切换会话时回填 */
  history?: MessageItem[]
  /** 一轮对话结束（成功或失败）后回调，用于刷新会话列表 */
  onFinish?: () => void
}

export function useChatStream(sessionId: string, options: UseChatStreamOptions = {}) {
  const { history, onFinish } = options
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [riskLevel, setRiskLevel] = useState<RiskLevel | null>(null)
  const [intent, setIntent] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const lastSessionRef = useRef<string | null>(null)
  /** 本会话是否已产生本地消息：避免历史回填覆盖正在进行的对话 */
  const dirtyRef = useRef(false)
  const onFinishRef = useRef(onFinish)
  onFinishRef.current = onFinish

  useEffect(() => {
    if (lastSessionRef.current !== sessionId) {
      lastSessionRef.current = sessionId
      dirtyRef.current = false
      setRiskLevel(null)
      setIntent(null)
    }
    if (dirtyRef.current) return
    setMessages((history ?? []).map(fromHistoryItem))
  }, [sessionId, history])

  useEffect(() => () => abortRef.current?.abort(), [])

  const patch = useCallback((id: string, updater: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? updater(m) : m)))
  }, [])

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      const content = text.trim()
      if (!content || loading || !sessionId) return

      const assistantId = uid()
      dirtyRef.current = true
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: 'user', content, steps: [] },
        { id: assistantId, role: 'assistant', content: '', steps: [], streaming: true },
      ])
      setLoading(true)

      const controller = new AbortController()
      abortRef.current = controller
      const collected: Citation[] = []

      const handlers: ChatHandlers = {
        onMeta: (meta) => {
          setIntent(meta.intent || null)
          setRiskLevel(meta.risk_level ?? null)
          patch(assistantId, (m) => ({ ...m, scopeVerdict: meta.scope_verdict }))
        },
        onToken: (t) =>
          patch(assistantId, (m) => ({ ...m, content: m.content + (t.text ?? '') })),
        onCitation: (c) => {
          collected.push(c)
          patch(assistantId, (m) => ({ ...m, citations: [...collected] }))
        },
        onAgentStep: (s) =>
          patch(assistantId, (m) => ({
            ...m,
            steps: [
              ...m.steps,
              { id: uid(), kind: 'step', label: s.node ?? '节点', detail: s.detail },
            ],
          })),
        onToolCall: (t) =>
          patch(assistantId, (m) => ({
            ...m,
            steps: [
              ...m.steps,
              {
                id: uid(),
                kind: 'tool',
                label: t.tool ?? '工具',
                detail: t.args_preview,
                ok: t.ok,
              },
            ],
          })),
        onMemory: (mem) => {
          const used = mem.metrics_used?.length ? mem.metrics_used.join('、') : undefined
          patch(assistantId, (m) => ({
            ...m,
            steps: [
              ...m.steps,
              {
                id: uid(),
                kind: 'memory',
                label: mem.patient_id ? `患者 ${mem.patient_id} 纵向记忆` : '患者记忆',
                detail: used,
                ok: true,
              },
            ],
          }))
        },
        onHitl: (h) => {
          const reason = Array.isArray(h.reason) ? h.reason.join('；') : h.reason
          patch(assistantId, (m) => ({ ...m, hitl: reason || '已转人工医生复核' }))
          setRiskLevel((prev) => prev ?? 'urgent')
        },
        onQC: (q) => patch(assistantId, (m) => ({ ...m, qc: q })),
        onDone: (d) => {
          if (d.citations?.length) {
            patch(assistantId, (m) => ({ ...m, citations: d.citations }))
          } else if (d.final && !collected.length) {
            patch(assistantId, (m) => (m.content ? m : { ...m, content: d.final }))
          }
          patch(assistantId, (m) => ({ ...m, streaming: false }))
        },
        onError: (e) => {
          patch(assistantId, (m) => ({
            ...m,
            streaming: false,
            error: e.message || '本次回复失败，请重试',
          }))
        },
      }

      try {
        await streamChat(sessionId, content, handlers, {
          token: useSessionStore.getState().token ?? undefined,
          signal: controller.signal,
        })
      } finally {
        // 兜底：流异常中断也要解除 streaming，避免界面一直转圈
        patch(assistantId, (m) => ({ ...m, streaming: false }))
        setLoading(false)
        abortRef.current = null
        onFinishRef.current?.()
      }
    },
    [sessionId, loading, patch],
  )

  const clear = useCallback(() => {
    dirtyRef.current = true
    setMessages([])
    setRiskLevel(null)
    setIntent(null)
  }, [])

  const retryLast = useCallback(() => {
    const last = [...messages].reverse().find((m) => m.role === 'user')
    if (!last) return
    setMessages((prev) => prev.filter((m) => !(m.role === 'assistant' && m.error)))
    void sendMessage(last.content)
  }, [messages, sendMessage])

  return { messages, loading, riskLevel, intent, sendMessage, stop, clear, retryLast }
}
