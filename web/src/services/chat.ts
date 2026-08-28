import { useSessionStore } from '@/stores/session'
import type {
  ChatHandlers,
  Citation,
  SSEAgentStep,
  SSECorrection,
  SSEDone,
  SSEError,
  SSEHitl,
  SSEMemory,
  SSEMeta,
  SSEQC,
  SSEToolCall,
  SSEToken,
} from '@/types/contract'

/**
 * SSE 解析器（手写状态机）
 *
 * 按 `event:` / `data:` 行切分，块与块之间以空行分隔。
 * 之所以不用 EventSource：后端是 POST SSE，EventSource 只支持 GET。
 * 保留原因：解析器已有 3 个单测用例覆盖（chat.test.ts），含中文 token 被截断的增量场景。
 */
export function createSSEParser(handlers: ChatHandlers) {
  let buffer = ''
  let eventType = ''
  let dataLines: string[] = []

  const emit = (type: string, rawData: string) => {
    let data: unknown
    if (rawData) {
      try {
        data = JSON.parse(rawData)
      } catch {
        // 单块 JSON 损坏不应中断整条流，降级为 error 事件交由上层渲染错误态
        handlers.onError?.({
          code: 'sse_parse_error',
          message: '流式响应解析失败，已中断本次回复',
        })
        return
      }
    }

    switch (type) {
      case 'meta':
        handlers.onMeta?.(data as SSEMeta)
        break
      case 'token':
        handlers.onToken?.(data as SSEToken)
        break
      case 'citation':
        handlers.onCitation?.(data as Citation)
        break
      case 'hitl':
        handlers.onHitl?.(data as SSEHitl)
        break
      case 'qc':
        handlers.onQC?.(data as SSEQC)
        break
      case 'correction':
        handlers.onCorrection?.(data as SSECorrection)
        break
      case 'done':
        handlers.onDone?.(data as SSEDone)
        break
      case 'error':
        handlers.onError?.(data as SSEError)
        break
      case 'agent_step':
        handlers.onAgentStep?.(data as SSEAgentStep)
        break
      case 'tool_call':
        handlers.onToolCall?.(data as SSEToolCall)
        break
      case 'memory':
        handlers.onMemory?.(data as SSEMemory)
        break
      default:
        // 后端新增事件时前端不丢数据，避免"静默无反应"
        handlers.onUnknown?.(type, data)
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
      // 兼容 CRLF
      const trimmed = line.endsWith('\r') ? line.slice(0, -1) : line
      if (trimmed === '') {
        dispatch()
        continue
      }
      if (trimmed.startsWith('event:')) {
        eventType = trimmed.slice(6).trim()
        continue
      }
      if (trimmed.startsWith('data:')) {
        dataLines.push(trimmed.slice(5).trim())
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
  // SSE 必须携带凭证：默认取当前登录态，杜绝匿名请求
  const token = options.token ?? useSessionStore.getState().token

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(`${base}/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ session_id: sessionId, message }),
      signal: options.signal,
    })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      handlers.onError?.({ code: 'aborted', message: '已停止本次回复' })
      return
    }
    handlers.onError?.({ code: 'network_error', message: '无法连接服务，请确认后端已启动' })
    return
  }

  if (!res.ok) {
    let message = `请求失败 (${res.status})`
    try {
      const body = (await res.json()) as { message?: string; detail?: unknown }
      if (body?.message) message = body.message
      else if (typeof body?.detail === 'string') message = body.detail
    } catch {
      /* 忽略解析失败，保留默认文案 */
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
