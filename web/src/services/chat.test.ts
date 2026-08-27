import { describe, it, expect } from 'vitest'
import { createSSEParser } from '@/services/chat'
import type { ChatHandlers } from '@/types/contract'

function makeSSE(parts: string[]): string {
  return parts.join('\n')
}

const fullStream = makeSSE([
  'event: meta',
  'data: {"session_id":"s1","intent":"triage","risk_level":"routine"}',
  '',
  'event: token',
  'data: {"text":"白细胞"}',
  '',
  'event: token',
  'data: {"text":"偏高"}',
  '',
  'event: citation',
  'data: {"index":0,"source":"FDA","snippet":"ref range"}',
  '',
  'event: qc',
  'data: {"status":"passed","risk_score":0.2,"violations":[]}',
  '',
  'event: done',
  'data: {"final":"报告","citations":[{"index":0,"source":"FDA","snippet":"ref range"}]}',
  '',
])

describe('createSSEParser', () => {
  it('dispatches all event types in order and concatenates tokens', () => {
    const tokens: string[] = []
    const handlers: ChatHandlers = {
      onMeta: (m) => expect(m).toEqual({ session_id: 's1', intent: 'triage', risk_level: 'routine' }),
      onToken: (t) => tokens.push(t.text),
      onCitation: (c) => expect(c.index).toBe(0),
      onQC: (q) => expect(q.status).toBe('passed'),
      onDone: (d) => expect(d.citations).toHaveLength(1),
    }
    const parser = createSSEParser(handlers)
    parser.push(fullStream)
    parser.flush()
    expect(tokens).toEqual(['白细胞', '偏高'])
    expect(tokens.join('')).toBe('白细胞偏高')
  })

  it('parses incrementally when chunks split lines', () => {
    const tokens: string[] = []
    const parser = createSSEParser({ onToken: (t) => tokens.push(t.text) })
    for (const ch of fullStream) parser.push(ch)
    parser.flush()
    expect(tokens.join('')).toBe('白细胞偏高')
  })

  it('dispatches error events', () => {
    let received: unknown
    const parser = createSSEParser({ onError: (e) => (received = e) })
    parser.push(
      makeSSE(['event: error', 'data: {"code":"INVALID","message":"bad input"}', '']),
    )
    parser.flush()
    expect(received).toEqual({ code: 'INVALID', message: 'bad input' })
  })
})
