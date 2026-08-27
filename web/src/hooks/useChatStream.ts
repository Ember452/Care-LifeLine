import { useCallback, useEffect, useState } from 'react'
import { streamChat } from '@/services/chat'
import type { ChatHandlers, Citation, SSEQC } from '@/types/contract'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  qc?: SSEQC
}

function uid(): string {
  return crypto.randomUUID()
}

export function useChatStream(sessionId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [riskLevel, setRiskLevel] = useState<string | null>(null)

  useEffect(() => {
    setMessages([])
    setRiskLevel(null)
  }, [sessionId])

  const sendMessage = useCallback(
    async (text: string) => {
      const content = text.trim()
      if (!content || loading) return

      const assistantId = uid()
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: 'user', content },
        { id: assistantId, role: 'assistant', content: '' },
      ])
      setLoading(true)

      const citations: Citation[] = []
      const handlers: ChatHandlers = {
        onToken: (t) =>
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + t.text } : m)),
          ),
        onCitation: (c) => {
          citations.push(c)
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, citations: [...citations] } : m)),
          )
        },
        onQC: (q: SSEQC) => {
          setRiskLevel(q.status)
          setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, qc: q } : m)))
        },
        onDone: (d) => {
          if (d.citations.length) {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, citations: d.citations } : m)),
            )
          }
        },
        onError: (e) =>
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: `${m.content}\n\n[错误] ${e.message}` } : m,
            ),
          ),
      }

      await streamChat(sessionId, content, handlers)
      setLoading(false)
    },
    [sessionId, loading],
  )

  return { messages, loading, riskLevel, sendMessage }
}
