import type { Citation } from '@/types/contract'

export default function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div
      style={{
        border: '1px solid #e5e6eb',
        borderRadius: 8,
        padding: '8px 12px',
        background: 'var(--bg-page)',
      }}
    >
      <div style={{ color: 'var(--brand-500)', fontSize: 13, fontWeight: 600 }}>
        [{citation.index}] {citation.source}
      </div>
      <div style={{ color: 'var(--text-2)', fontSize: 13, marginTop: 4 }}>{citation.snippet}</div>
    </div>
  )
}
