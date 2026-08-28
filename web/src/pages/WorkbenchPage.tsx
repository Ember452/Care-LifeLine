import { useEffect, useState } from 'react'
import { Button, Input, Message, Space, Tag } from '@arco-design/web-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workbenchApi } from '@/services/api'
import PageContainer from '@/components/PageContainer'
import { AsyncState } from '@/components/StateBlock'
import Markdown from '@/components/Markdown'
import { formatTime, violationText } from '@/utils/format'

export default function WorkbenchPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editing, setEditing] = useState(false)
  const [editedText, setEditedText] = useState('')

  /* ------------------------------ 待审队列 ------------------------------ */
  const queueQuery = useQuery({
    queryKey: ['workbench-queue'],
    queryFn: workbenchApi.queue,
    refetchInterval: 15_000,
  })
  const queue = queueQuery.data ?? []

  useEffect(() => {
    if (selectedId === null && queue.length > 0) setSelectedId(Number(queue[0].id))
    else if (selectedId !== null && queue.length > 0 && !queue.some((q) => Number(q.id) === selectedId)) {
      setSelectedId(Number(queue[0].id))
    }
  }, [queue, selectedId])

  /* ------------------------------ 审核详情 ------------------------------ */
  const itemQuery = useQuery({
    queryKey: ['workbench-item', selectedId],
    queryFn: () => workbenchApi.item(selectedId as number),
    enabled: selectedId !== null,
  })
  const item = itemQuery.data

  /* ------------------------------ 审核动作 ------------------------------ */
  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['workbench-queue'] })
    void queryClient.invalidateQueries({ queryKey: ['workbench-item'] })
    void queryClient.invalidateQueries({ queryKey: ['admin-metrics'] })
  }

  const review = useMutation({
    mutationFn: ({ decision, correctedText }: { decision: 'approve' | 'reject' | 'revise'; correctedText?: string }) =>
      workbenchApi.review(selectedId as number, decision, correctedText),
    onSuccess: () => {
      Message.success('已提交审核结果')
      setEditing(false)
      invalidateAll()
    },
    onError: (e) => {
      Message.error(e instanceof Error ? e.message : '审核失败')
    },
  })

  const doApprove = () => review.mutate({ decision: 'approve' })
  const doReject = () => review.mutate({ decision: 'reject' })
  const doRevise = () => {
    const v = editedText.trim()
    if (!v) {
      Message.warning('请填写修正后的回复')
      return
    }
    review.mutate({ decision: 'revise', correctedText: v })
  }

  return (
    <PageContainer title="医生审核台" subtitle="复核 AI 生成的回复，决定通过、驳回或修正">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 340px) 1fr', gap: 16, alignItems: 'start' }}>
        {/* 左：待审队列 */}
        <div className="care-card" style={{ display: 'flex', flexDirection: 'column', minHeight: 480, maxHeight: 'calc(100vh - 180px)' }}>
          <div className="care-card-head">
            <span style={{ fontSize: 13, fontWeight: 600 }}>待审队列</span>
            <Tag color={queue.length > 0 ? 'orange' : 'green'}>{queue.length} 条</Tag>
          </div>
          <div className="care-scroll" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            <AsyncState
              loading={queueQuery.isLoading}
              error={queueQuery.error}
              onRetry={() => void queryClient.invalidateQueries({ queryKey: ['workbench-queue'] })}
              isEmpty={queue.length === 0}
              empty={<div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>暂无待审核项</div>}
            >
              {queue.map((q) => {
                const active = Number(q.id) === selectedId
                return (
                  <div
                    key={q.id}
                    onClick={() => setSelectedId(Number(q.id))}
                    style={{
                      padding: '10px 16px',
                      cursor: 'pointer',
                      background: active ? 'var(--brand-100)' : 'transparent',
                      borderLeft: active ? '3px solid var(--brand-500)' : '3px solid transparent',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: active ? 'var(--brand-500)' : 'var(--text-1)' }}>
                        #{q.id}
                      </span>
                      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{formatTime(q.created_at)}</span>
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: 'var(--text-3)',
                        marginTop: 4,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {q.draft || '（无草稿）'}
                    </div>
                    {q.violations.length > 0 && (
                      <Tag color="red" size="small" style={{ marginTop: 4 }}>
                        {q.violations.length} 项违规
                      </Tag>
                    )}
                  </div>
                )
              })}
            </AsyncState>
          </div>
        </div>

        {/* 右：审核详情 */}
        <div className="care-card" style={{ padding: 16, minHeight: 480 }}>
          <AsyncState
            loading={itemQuery.isLoading && selectedId !== null}
            error={itemQuery.error}
            onRetry={() => void queryClient.invalidateQueries({ queryKey: ['workbench-item'] })}
            isEmpty={!item}
            empty={<div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>选择左侧待审项查看详情</div>}
          >
            {item && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* 原文 */}
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 6 }}>用户提问</div>
                  <div style={{ background: 'var(--bg-sunken)', borderRadius: 8, padding: '10px 14px', fontSize: 14, color: 'var(--text-1)' }}>
                    {item.input_text || '—'}
                  </div>
                </div>

                {/* draft */}
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 6 }}>AI 回复草稿</div>
                  {editing ? (
                    <Input.TextArea
                      value={editedText}
                      onChange={setEditedText}
                      autoSize={{ minRows: 8, maxRows: 16 }}
                      style={{ fontSize: 14 }}
                    />
                  ) : (
                    <div
                      style={{
                        background: 'var(--bg-sunken)',
                        borderRadius: 8,
                        padding: '12px 14px',
                        fontSize: 14,
                      }}
                    >
                      <Markdown content={item.draft || '—'} />
                    </div>
                  )}
                </div>

                {/* 违规项 */}
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 6 }}>质控违规项</div>
                  {item.violations.length === 0 ? (
                    <Tag color="green">未发现违规</Tag>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {item.violations.map((v, i) => (
                        <div
                          key={i}
                          style={{
                            background: 'var(--danger-bg)',
                            color: 'var(--danger)',
                            borderRadius: 6,
                            padding: '8px 12px',
                            fontSize: 13,
                          }}
                        >
                          {violationText(v)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 状态与审核动作 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 13, color: 'var(--text-3)' }}>
                    状态：{item.status === 'pending' ? '待审核' : item.status}
                    {item.decided_by ? ` · 审核人 ${item.decided_by}` : ''}
                  </span>
                  <div style={{ flex: 1 }} />
                  {item.status === 'pending' && (
                    <Space size={8}>
                      {editing ? (
                        <>
                          <Button onClick={() => { setEditing(false); setEditedText('') }}>取消</Button>
                          <Button type="primary" loading={review.isPending} onClick={doRevise}>
                            提交修正
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button type="primary" loading={review.isPending} onClick={doApprove}>
                            通过
                          </Button>
                          <Button status="danger" loading={review.isPending} onClick={doReject}>
                            驳回
                          </Button>
                          <Button
                            onClick={() => {
                              setEditedText(item.draft ?? '')
                              setEditing(true)
                            }}
                          >
                            修正
                          </Button>
                        </>
                      )}
                    </Space>
                  )}
                </div>
              </div>
            )}
          </AsyncState>
        </div>
      </div>
    </PageContainer>
  )
}
