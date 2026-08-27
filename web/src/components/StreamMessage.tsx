import { useState } from 'react'
import { Tag } from '@arco-design/web-react'
import type { ChatMessage } from '@/hooks/useChatStream'
import Markdown from './Markdown'
import CitationCard from './CitationCard'

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
      {qc?.status === 'hitl' && (
        <div
          style={{
            background: '#fff3e8',
            color: 'var(--warning)',
            border: '1px solid #ffd9a8',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: 13,
            marginBottom: 8,
          }}
        >
          ⚠️ 检测到高风险场景，已转接人工医生复核。
        </div>
      )}
      {qc?.status === 'refused' && (
        <div
          style={{
            background: '#f2f3f5',
            color: 'var(--text-3)',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: 13,
            marginBottom: 8,
          }}
        >
          该请求无法提供回复。
        </div>
      )}
      <div
        style={{
          background: 'var(--bg-card)',
          padding: '12px 16px',
          borderRadius: '8px 8px 8px 0',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <Markdown content={message.content} />
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
