import { useEffect, useRef, useState } from 'react'
import { Button, Input, Popconfirm, Tag } from '@arco-design/web-react'
import { IconDelete, IconPlus, IconStop } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sessionApi, sessionKey } from '@/services/api'
import { useChatStream } from '@/hooks/useChatStream'
import StreamMessage from '@/components/StreamMessage'
import EmptyState from '@/components/EmptyState'
import { AsyncState } from '@/components/StateBlock'
import { useSessionStore } from '@/stores/session'
import { intentLabel, RISK_LABEL, formatDate } from '@/utils/format'

export default function ChatPage() {
  const queryClient = useQueryClient()
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const setActiveSessionId = useSessionStore((s) => s.setActiveSessionId)

  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  /* ------------------------------ 会话列表 ------------------------------ */
  const sessionsQuery = useQuery({
    queryKey: ['sessions'],
    queryFn: sessionApi.list,
    staleTime: 0,
  })
  const sessions = sessionsQuery.data ?? []

  const createMutation = useMutation({
    mutationFn: () => sessionApi.create('新对话'),
    onSuccess: (s) => {
      setActiveSessionId(sessionKey(s))
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => sessionApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
      void queryClient.invalidateQueries({ queryKey: ['messages'] })
    },
  })

  // 首次进入无会话时自动新建，避免"没有会话没法聊"的死角
  // 仅当从未发起过创建时触发（isIdle），失败后不自动重试，防止循环请求
  useEffect(() => {
    if (sessionsQuery.isSuccess && sessions.length === 0 && createMutation.isIdle) {
      createMutation.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionsQuery.isSuccess, sessions.length, createMutation.isIdle])

  // 当前激活会话：无则回落第一个；被删除则回落剩余第一个
  useEffect(() => {
    if (!activeSessionId && sessions.length) setActiveSessionId(sessionKey(sessions[0]))
    else if (activeSessionId && sessions.length && !sessions.some((s) => sessionKey(s) === activeSessionId)) {
      setActiveSessionId(sessionKey(sessions[0]))
    }
  }, [sessions, activeSessionId, setActiveSessionId])

  const activeId = sessions.some((s) => sessionKey(s) === activeSessionId) ? activeSessionId : null
  const activeSession = sessions.find((s) => sessionKey(s) === activeSessionId)

  /* ------------------------------ 历史消息 ------------------------------ */
  const historyQuery = useQuery({
    queryKey: ['messages', activeId],
    queryFn: () => sessionApi.messages(activeId as string),
    enabled: !!activeId,
  })

  /* ------------------------------ 流式对话 ------------------------------ */
  const { messages, loading, riskLevel, intent, sendMessage, stop } = useChatStream(activeId ?? '', {
    history: historyQuery.data,
    onFinish: () => {
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  // 新消息自动滚到底
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length])

  const submit = (text: string) => {
    const value = text.trim()
    if (!value || loading || !activeId) return
    sendMessage(value)
    setInput('')
  }

  const onDelete = (id: string) => {
    if (id === activeSessionId) setActiveSessionId(null)
    deleteMutation.mutate(id)
  }

  const chatReady = !!activeId
  const showSkeleton = sessionsQuery.isLoading || (sessions.length === 0 && createMutation.isPending)

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* 左侧会话列表 */}
      <div
        style={{
          width: 240,
          flexShrink: 0,
          borderRight: '1px solid var(--border)',
          background: 'var(--bg-card)',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}
      >
        <div style={{ padding: 12 }}>
          <Button long type="primary" disabled={createMutation.isPending} onClick={() => createMutation.mutate()}>
            <IconPlus /> 新建会话
          </Button>
        </div>
        <div className="care-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
          <AsyncState
            loading={sessionsQuery.isLoading}
            error={sessionsQuery.error}
            onRetry={() => void queryClient.invalidateQueries({ queryKey: ['sessions'] })}
            isEmpty={sessions.length === 0}
            empty={<div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>暂无会话</div>}
          >
            {sessions.map((s) => {
              const sid = sessionKey(s)
              const active = sid === activeSessionId
              return (
                <div
                  key={sid}
                  onClick={() => setActiveSessionId(sid)}
                  style={{
                    padding: '10px 12px 10px 16px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    background: active ? 'var(--brand-100)' : 'transparent',
                    borderLeft: active ? '3px solid var(--brand-500)' : '3px solid transparent',
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 14,
                        color: active ? 'var(--brand-500)' : 'var(--text-1)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontWeight: active ? 600 : 400,
                      }}
                    >
                      {s.title || '新对话'}
                    </div>
                    {s.created_at && (
                      <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
                        {formatDate(s.created_at)}
                      </div>
                    )}
                  </div>
                  <Popconfirm
                    title="删除该会话？"
                    okText="删除"
                    cancelText="取消"
                    onOk={() => onDelete(sid)}
                  >
                    <Button
                      size="mini"
                      type="text"
                      status="danger"
                      icon={<IconDelete />}
                      onClick={(e) => e.stopPropagation()}
                      style={{ visibility: active ? 'visible' : 'hidden' }}
                    />
                  </Popconfirm>
                </div>
              )
            })}
          </AsyncState>
        </div>
      </div>

      {/* 右侧对话区 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div
          style={{
            height: 52,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '0 20px',
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg-card)',
          }}
        >
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-1)' }}>
            {activeSession?.title || '智能问诊'}
          </span>
          {intent && <Tag color="arcoblue" size="small">{intentLabel(intent)}</Tag>}
          {riskLevel && (
            <Tag
              size="small"
              color={riskLevel === 'critical' ? 'red' : riskLevel === 'urgent' ? 'orange' : 'green'}
            >
              {RISK_LABEL[riskLevel]}
            </Tag>
          )}
        </div>

        <div ref={scrollRef} className="care-scroll" style={{ flex: 1, overflowY: 'auto', padding: '0 24px' }}>
          {showSkeleton ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 24 }}>
              <div className="care-skeleton-bar" style={{ height: 52 }} />
              <div className="care-skeleton-bar" style={{ height: 52 }} />
            </div>
          ) : messages.length === 0 ? (
            <EmptyState onExample={() => submit('最近化验单提示贫血，需要注意什么？')} />
          ) : (
            messages.map((m) => <StreamMessage key={m.id} message={m} />)
          )}
        </div>

        <div
          style={{
            borderTop: '1px solid var(--border)',
            padding: 16,
            display: 'flex',
            gap: 8,
            alignItems: 'flex-end',
            background: 'var(--bg-card)',
          }}
        >
          <Input.TextArea
            value={input}
            onChange={setInput}
            disabled={!chatReady || loading}
            placeholder={chatReady ? '描述您的症状，回车发送…' : '会话创建中，请稍候…'}
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={() => submit(input)}
            style={{ flex: 1 }}
          />
          {loading ? (
            <Button type="primary" status="warning" icon={<IconStop />} onClick={stop}>
              停止
            </Button>
          ) : (
            <Button type="primary" disabled={!chatReady || !input.trim()} onClick={() => submit(input)}>
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
