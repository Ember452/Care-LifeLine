import { useState } from 'react'
import { Button, Input } from '@arco-design/web-react'
import { useChatStream } from '@/hooks/useChatStream'
import StreamMessage from '@/components/StreamMessage'
import EmptyState from '@/components/EmptyState'

interface LocalSession {
  id: string
  title: string
}

function uid(): string {
  return crypto.randomUUID()
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<LocalSession[]>(() => [{ id: uid(), title: '新对话' }])
  const [activeId, setActiveId] = useState<string>(() => sessions[0].id)
  const [input, setInput] = useState('')
  const { messages, loading, riskLevel, sendMessage } = useChatStream(activeId)

  const submit = (text: string) => {
    const value = text.trim()
    if (!value || loading) return
    sendMessage(value)
    setSessions((prev) =>
      prev.map((s) => (s.id === activeId && s.title === '新对话' ? { ...s, title: value.slice(0, 12) } : s)),
    )
    setInput('')
  }

  const newSession = () => {
    const id = uid()
    setSessions((prev) => [...prev, { id, title: '新对话' }])
    setActiveId(id)
  }

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div
        style={{
          width: 240,
          borderRight: '1px solid #f0f0f0',
          background: 'var(--bg-card)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Button long type="primary" style={{ margin: 12 }} onClick={newSession}>
          + 新对话
        </Button>
        <div style={{ overflow: 'auto', flex: 1 }}>
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => setActiveId(s.id)}
              style={{
                padding: '10px 16px',
                cursor: 'pointer',
                background: s.id === activeId ? 'var(--brand-100)' : 'transparent',
                color: s.id === activeId ? 'var(--brand-500)' : 'var(--text-1)',
                fontSize: 14,
              }}
            >
              {s.title}
            </div>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {riskLevel === 'hitl' && (
          <div
            style={{
              background: '#fff3e8',
              color: 'var(--warning)',
              padding: '8px 24px',
              fontSize: 13,
              borderBottom: '1px solid #ffd9a8',
            }}
          >
            ⚠️ 本次会话已标记为高风险，转人工医生复核。
          </div>
        )}
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {messages.length === 0 ? (
            <EmptyState onExample={() => submit('最近化验单说贫血，需要注意什么？')} />
          ) : (
            messages.map((m) => <StreamMessage key={m.id} message={m} />)
          )}
        </div>
        <div style={{ borderTop: '1px solid #f0f0f0', padding: 16, display: 'flex', gap: 8 }}>
          <Input.TextArea
            value={input}
            onChange={setInput}
            disabled={loading}
            placeholder="描述您的症状，回车发送…"
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={() => submit(input)}
          />
          <Button type="primary" loading={loading} disabled={!input.trim()} onClick={() => submit(input)}>
            发送
          </Button>
        </div>
      </div>
    </div>
  )
}
