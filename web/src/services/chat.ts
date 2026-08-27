import type { ChatHandlers } from '@/types/contract'

export function createSSEParser(handlers: ChatHandlers) {
  let buffer = ''
  let eventType = ''
  let dataLines: string[] = []

  const emit = (type: string, rawData: string) => {
    const data = rawData ? JSON.parse(rawData) : undefined
    switch (type) {
      case 'meta':
        handlers.onMeta?.(data)
        break
      case 'token':
        handlers.onToken?.(data)
        break
      case 'citation':
        handlers.onCitation?.(data)
        break
      case 'qc':
        handlers.onQC?.(data)
        break
      case 'correction':
        handlers.onCorrection?.(data)
        break
      case 'done':
        handlers.onDone?.(data)
        break
      case 'error':
        handlers.onError?.(data)
        break
    }
  }

  const dispatch = () => {
    if (eventType || dataLines.length) {
      emit(eventType, dataLines.join('\n'))
    }
    eventType = ''
    dataLines = []
  }

  const push = (chunk: string) => {
    buffer += chunk
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line === '') {
        dispatch()
        continue
      }
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
        continue
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
        continue
      }
    }
  }

  const flush = () => {
    dispatch()
    buffer = ''
  }

  return { push, flush }
}

export interface StreamChatOptions {
  baseURL?: string
  token?: string
  signal?: AbortSignal
}

export async function streamChat(
  sessionId: string,
  message: string,
  handlers: ChatHandlers,
  options: StreamChatOptions = {},
): Promise<void> {
  const base = options.baseURL ?? '/v1'
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options.token) headers['Authorization'] = `Bearer ${options.token}`

  const res = await fetch(`${base}/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ session_id: sessionId, message }),
    signal: options.signal,
  })

  if (!res.ok) {
    let message = `请求失败 (${res.status})`
    try {
      const body = await res.json()
      if (body?.message) message = body.message
    } catch {
      /* ignore parse error */
    }
    handlers.onError?.({ code: String(res.status), message })
    return
  }

  if (!res.body) {
    handlers.onError?.({ code: 'NO_BODY', message: '空响应' })
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  const parser = createSSEParser(handlers)

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.flush()
}
