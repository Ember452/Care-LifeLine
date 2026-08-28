import { useState } from 'react'
import { Button, Input, Tag } from '@arco-design/web-react'
import { useMutation } from '@tanstack/react-query'
import { reportApi } from '@/services/api'
import PageContainer from '@/components/PageContainer'
import CitationCard from '@/components/CitationCard'
import { EmptyBlock, ErrorBlock, LoadingSkeleton } from '@/components/StateBlock'

const EXAMPLE = '血压：150/95 mmHg，空腹血糖：7.8 mmol/L，总胆固醇：5.9 mmol/L'

export default function ReportPage() {
  const [text, setText] = useState('')

  const interpret = useMutation({
    mutationFn: (value: string) => reportApi.interpret(value),
  })

  const submit = (value: string) => {
    const v = value.trim()
    if (!v || interpret.isPending) return
    interpret.mutate(v)
  }

  const result = interpret.data

  return (
    <PageContainer
      title="报告解读"
      subtitle="粘贴检验报告文本，自动提取指标并标注异常项"
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 380px) 1fr', gap: 16, alignItems: 'start' }}>
        {/* 左：输入 */}
        <div className="care-card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Input.TextArea
            value={text}
            onChange={setText}
            placeholder={`粘贴检验报告文本，支持一行多指标\n\n示例：${EXAMPLE}`}
            autoSize={{ minRows: 8, maxRows: 16 }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <Button type="primary" loading={interpret.isPending} disabled={!text.trim()} onClick={() => submit(text)}>
              解读报告
            </Button>
            <Button onClick={() => setText(EXAMPLE)}>填入示例</Button>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            解读结果仅供辅助参考，不能替代医生诊断。
          </div>
        </div>

        {/* 右：结果 */}
        <div>
          {interpret.isPending ? (
            <div className="care-card" style={{ padding: 16 }}>
              <LoadingSkeleton rows={4} />
            </div>
          ) : interpret.isError ? (
            <div className="care-card" style={{ padding: 16 }}>
              <ErrorBlock error={interpret.error} onRetry={() => submit(text)} />
            </div>
          ) : !result ? (
            <div className="care-card">
              <EmptyBlock title="等待输入" description="在左侧粘贴报告文本，点击「解读报告」查看结构化结果" />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {result.summary && (
                <div className="care-card" style={{ padding: 16 }}>
                  <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 4 }}>概览</div>
                  <div style={{ fontSize: 14, color: 'var(--text-1)', lineHeight: 1.7 }}>{result.summary}</div>
                </div>
              )}

              {result.fields.length > 0 ? (
                <div className="care-card" style={{ padding: 16 }}>
                  <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 8 }}>指标解析（{result.fields.length} 项）</div>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {result.fields.map((f, i) => (
                      <div
                        key={`${f.name}-${i}`}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '1fr 120px 1fr 72px',
                          gap: 8,
                          alignItems: 'center',
                          padding: '10px 8px',
                          borderBottom: i < result.fields.length - 1 ? '1px solid var(--border)' : 'none',
                          fontSize: 14,
                        }}
                      >
                        <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>{f.name}</span>
                        <span
                          className="num"
                          style={{
                            color: f.abnormal ? 'var(--danger)' : 'var(--text-1)',
                            fontWeight: f.abnormal ? 600 : 400,
                          }}
                        >
                          {f.value}
                        </span>
                        <span style={{ color: 'var(--text-3)', fontSize: 13 }}>{f.reference || '—'}</span>
                        {f.abnormal ? (
                          <Tag color="red" size="small" style={{ justifySelf: 'start' }}>异常</Tag>
                        ) : (
                          <span style={{ color: 'var(--success)', fontSize: 13 }}>正常</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="care-card">
                  <EmptyBlock title="未解析出指标" description="请检查报告文本是否包含可识别的检验项目" />
                </div>
              )}

              {result.citations.length > 0 && (
                <div className="care-card" style={{ padding: 16 }}>
                  <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 8 }}>参考资料</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {result.citations.map((c) => (
                      <CitationCard key={c.index} citation={c} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </PageContainer>
  )
}
