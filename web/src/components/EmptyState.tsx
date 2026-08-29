import { IconPlusCircle } from '@arco-design/web-react/icon'

const EXAMPLES = [
  { text: '最近头晕、血压偏高，需要注意什么？', tag: '症状分诊' },
  { text: '华法林和阿司匹林能一起吃吗？', tag: '用药咨询' },
  { text: '血压：150/95 mmHg（参考范围 <140/90），帮我看看', tag: '报告解读' },
]

export default function EmptyState({ onExample }: { onExample?: (text: string) => void }) {
  return (
    <div
      style={{
        minHeight: '60%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 16,
          background: 'var(--brand-50)',
          border: '1px solid var(--brand-100)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
          fontSize: 26,
          color: 'var(--brand-500)',
          fontWeight: 700,
        }}
      >
        ⚕
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-1)', marginBottom: 6 }}>
        您好，我是健康分诊助手
      </div>
      <div style={{ fontSize: 14, color: 'var(--text-3)', marginBottom: 24, lineHeight: 1.7 }}>
        可以描述症状、上传报告或咨询用药
        <br />
        回复均附带指南引用与免责声明，急症会自动转人工
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center' }}>
        {EXAMPLES.map((e) => (
          <button key={e.tag} type="button" className="care-hero-chip" onClick={() => onExample?.(e.text)}>
            <IconPlusCircle style={{ marginRight: 6, fontSize: 13, verticalAlign: -2 }} />
            <span style={{ color: 'var(--text-3)', marginRight: 6 }}>{e.tag}</span>
            {e.text}
          </button>
        ))}
      </div>
    </div>
  )
}
