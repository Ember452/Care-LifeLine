import { useState } from 'react'
import { Button, Card, Input, Message, Popconfirm, Radio, Select, Tag } from '@arco-design/web-react'
import { IconCheck, IconClose, IconPlus } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memoryApi, patientApi } from '@/services/api'
import type { PatientItem } from '@/types/contract'
import PageContainer from '@/components/PageContainer'
import { AsyncState } from '@/components/StateBlock'
import EmptyState from '@/components/EmptyState'
import { formatDate } from '@/utils/format'

/** 溯源标签：记忆条目的信任基础（医生录入 > 患者自述 > 会话抽取） */
const PROVENANCE_META: Record<string, { label: string; color: string }> = {
  clinician: { label: '医生录入', color: 'green' },
  user: { label: '患者自述', color: 'arcoblue' },
  extracted: { label: '会话抽取', color: 'purple' },
}

function ProvenanceTag({ provenance }: { provenance?: string }) {
  const meta = PROVENANCE_META[provenance ?? 'user'] ?? PROVENANCE_META.user
  return (
    <Tag size="small" color={meta.color} style={{ borderRadius: 999 }}>
      {meta.label}
    </Tag>
  )
}

const KIND_LABEL: Record<string, string> = {
  medication: '用药',
  allergy: '过敏',
  followup: '随访',
}

function ProposalsCard({ patientId }: { patientId: string }) {
  const queryClient = useQueryClient()
  const proposalsQuery = useQuery({
    queryKey: ['memory-proposals', patientId],
    queryFn: () => memoryApi.proposals(patientId),
    enabled: !!patientId,
  })
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['memory-proposals', patientId] })
    void queryClient.invalidateQueries({ queryKey: ['memory-meds', patientId] })
    void queryClient.invalidateQueries({ queryKey: ['memory-allergies', patientId] })
    void queryClient.invalidateQueries({ queryKey: ['memory-followups', patientId] })
  }
  const confirmMut = useMutation({
    mutationFn: (id: number) => memoryApi.confirmProposal(patientId, id),
    onSuccess: (r) => {
      Message.success(r.applied || '已确认')
      invalidate()
    },
  })
  const rejectMut = useMutation({
    mutationFn: (id: number) => memoryApi.rejectProposal(patientId, id),
    onSuccess: () => {
      Message.info('已驳回，未写入记忆')
      invalidate()
    },
  })

  const proposals = proposalsQuery.data ?? []
  if (!proposals.length) return null

  return (
    <Card
      className="care-card"
      title="待确认的记忆提议"
      extra={<span style={{ fontSize: 12, color: 'var(--text-3)' }}>来自对话抽取，确认后才写入档案</span>}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {proposals.map((p) => (
          <div
            key={p.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-sunken)',
            }}
          >
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 14 }}>
                <Tag size="small" color="purple">
                  {KIND_LABEL[p.kind] ?? p.kind}
                  {p.action === 'stop' ? ' · 停用' : ''}
                </Tag>
                <span style={{ fontWeight: 600 }}>
                  {p.payload.name || p.payload.allergen || p.payload.plan}
                </span>
              </div>
              {p.excerpt && (
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
                  依据：「{p.excerpt}」
                </div>
              )}
            </div>
            <Button
              size="small"
              type="primary"
              icon={<IconCheck />}
              loading={confirmMut.isPending}
              onClick={() => confirmMut.mutate(p.id)}
            >
              确认写入
            </Button>
            <Button size="small" icon={<IconClose />} onClick={() => rejectMut.mutate(p.id)}>
              驳回
            </Button>
          </div>
        ))}
      </div>
    </Card>
  )
}

function MedicationSection({ patientId }: { patientId: string }) {
  const queryClient = useQueryClient()
  const [includeHistory, setIncludeHistory] = useState(false)
  const [name, setName] = useState('')
  const [dosage, setDosage] = useState('')
  const query = useQuery({
    queryKey: ['memory-meds', patientId, includeHistory],
    queryFn: () => memoryApi.medications(patientId, includeHistory),
    enabled: !!patientId,
  })
  const addMut = useMutation({
    mutationFn: () => memoryApi.addMedication(patientId, { name: name.trim(), dosage: dosage.trim() || undefined }),
    onSuccess: () => {
      setName('')
      setDosage('')
      Message.success('已添加用药记录')
      void queryClient.invalidateQueries({ queryKey: ['memory-meds', patientId] })
    },
  })
  const stopMut = useMutation({
    mutationFn: (id: number) => memoryApi.stopMedication(patientId, id),
    onSuccess: () => {
      Message.success('已停用（历史保留可追溯）')
      void queryClient.invalidateQueries({ queryKey: ['memory-meds', patientId] })
    },
  })
  const items = query.data ?? []

  return (
    <Card className="care-card" title="用药史">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <Input placeholder="药名，如 华法林" value={name} onChange={setName} style={{ width: 180 }} />
        <Input placeholder="剂量/频次（可选）" value={dosage} onChange={setDosage} style={{ width: 200 }} />
        <Button type="primary" disabled={!name.trim()} loading={addMut.isPending} icon={<IconPlus />} onClick={() => addMut.mutate()}>
          添加
        </Button>
        <div style={{ marginLeft: 'auto' }}>
          <Radio.Group
            type="button"
            size="small"
            value={includeHistory ? 'history' : 'current'}
            onChange={(v) => setIncludeHistory(v === 'history')}
          >
            <Radio value="current">当前有效</Radio>
            <Radio value="history">含历史</Radio>
          </Radio.Group>
        </div>
      </div>
      <AsyncState loading={query.isLoading} error={query.error} isEmpty={items.length === 0}
        empty={<div style={{ color: 'var(--text-3)', fontSize: 13, padding: 12 }}>暂无用药记录</div>}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {items.map((m) => {
            const stopped = !!m.valid_to
            return (
              <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 4px', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontWeight: 600, color: stopped ? 'var(--text-3)' : 'var(--text-1)' }}>
                  {m.name}{stopped ? '（已停用）' : ''}
                </span>
                {m.dosage && <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{m.dosage}{m.frequency ? ` · ${m.frequency}` : ''}</span>}
                <ProvenanceTag provenance={m.provenance} />
                <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 'auto' }}>
                  {formatDate(m.valid_from ?? '')}
                  {stopped ? ` ~ ${formatDate(m.valid_to ?? '')}` : ''}
                </span>
                {!stopped && (
                  <Popconfirm title="确认停用该药物？" okText="停用" cancelText="取消" onOk={() => stopMut.mutate(m.id)}>
                    <Button size="mini" type="text" status="warning">停用</Button>
                  </Popconfirm>
                )}
              </div>
            )
          })}
        </div>
      </AsyncState>
    </Card>
  )
}

function AllergySection({ patientId }: { patientId: string }) {
  const queryClient = useQueryClient()
  const [allergen, setAllergen] = useState('')
  const [severity, setSeverity] = useState('moderate')
  const query = useQuery({
    queryKey: ['memory-allergies', patientId],
    queryFn: () => memoryApi.allergies(patientId),
    enabled: !!patientId,
  })
  const addMut = useMutation({
    mutationFn: () => memoryApi.addAllergy(patientId, { allergen: allergen.trim(), severity }),
    onSuccess: () => {
      setAllergen('')
      Message.success('已添加过敏记录')
      void queryClient.invalidateQueries({ queryKey: ['memory-allergies', patientId] })
    },
  })
  const deactivateMut = useMutation({
    mutationFn: (id: number) => memoryApi.deactivateAllergy(patientId, id),
    onSuccess: () => {
      Message.success('已标记失效（历史保留）')
      void queryClient.invalidateQueries({ queryKey: ['memory-allergies', patientId] })
    },
  })
  const items = (query.data ?? []).filter((a) => !a.valid_to)
  const SEVERITY_COLOR: Record<string, string> = { mild: 'green', moderate: 'orange', severe: 'red' }

  return (
    <Card className="care-card" title="过敏史">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <Input placeholder="过敏原，如 青霉素" value={allergen} onChange={setAllergen} style={{ width: 180 }} />
        <Select value={severity} onChange={setSeverity} style={{ width: 120 }}>
          <Select.Option value="mild">轻度</Select.Option>
          <Select.Option value="moderate">中度</Select.Option>
          <Select.Option value="severe">严重</Select.Option>
        </Select>
        <Button type="primary" disabled={!allergen.trim()} loading={addMut.isPending} icon={<IconPlus />} onClick={() => addMut.mutate()}>
          添加
        </Button>
      </div>
      <AsyncState loading={query.isLoading} error={query.error} isEmpty={items.length === 0}
        empty={<div style={{ color: 'var(--text-3)', fontSize: 13, padding: 12 }}>暂无过敏记录</div>}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {items.map((a) => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 4px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontWeight: 600 }}>{a.allergen}</span>
              <Tag size="small" color={SEVERITY_COLOR[a.severity ?? 'moderate']}>
                {a.severity === 'severe' ? '严重' : a.severity === 'mild' ? '轻度' : '中度'}
              </Tag>
              {a.reaction && <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{a.reaction}</span>}
              <ProvenanceTag provenance={a.provenance} />
              <Popconfirm title="标记为失效（误报/已脱敏）？" okText="失效" cancelText="取消" onOk={() => deactivateMut.mutate(a.id)}>
                <Button size="mini" type="text" status="warning" style={{ marginLeft: 'auto' }}>失效</Button>
              </Popconfirm>
            </div>
          ))}
        </div>
      </AsyncState>
    </Card>
  )
}

function FollowupSection({ patientId }: { patientId: string }) {
  const queryClient = useQueryClient()
  const [plan, setPlan] = useState('')
  const query = useQuery({
    queryKey: ['memory-followups', patientId],
    queryFn: () => memoryApi.followups(patientId),
    enabled: !!patientId,
  })
  const addMut = useMutation({
    mutationFn: () => memoryApi.addFollowup(patientId, { plan: plan.trim() }),
    onSuccess: () => {
      setPlan('')
      Message.success('已添加随访计划')
      void queryClient.invalidateQueries({ queryKey: ['memory-followups', patientId] })
    },
  })
  const doneMut = useMutation({
    mutationFn: (id: number) => memoryApi.completeFollowup(patientId, id),
    onSuccess: () => {
      Message.success('已完成')
      void queryClient.invalidateQueries({ queryKey: ['memory-followups', patientId] })
    },
  })
  const items = query.data ?? []
  const pending = items.filter((f) => f.status === 'pending')
  const done = items.filter((f) => f.status !== 'pending')

  return (
    <Card className="care-card" title="随访计划">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <Input placeholder="随访计划，如 两周后复查 INR" value={plan} onChange={setPlan} style={{ flex: 1 }} />
        <Button type="primary" disabled={!plan.trim()} loading={addMut.isPending} icon={<IconPlus />} onClick={() => addMut.mutate()}>
          添加
        </Button>
      </div>
      <AsyncState loading={query.isLoading} error={query.error} isEmpty={items.length === 0}
        empty={<div style={{ color: 'var(--text-3)', fontSize: 13, padding: 12 }}>暂无随访计划</div>}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {pending.map((f) => (
            <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 4px', borderBottom: '1px solid var(--border)' }}>
              <Tag size="small" color="orange">待办</Tag>
              <span style={{ fontWeight: 600 }}>{f.plan}</span>
              <ProvenanceTag provenance={f.provenance} />
              <Button size="mini" type="text" onClick={() => doneMut.mutate(f.id)} style={{ marginLeft: 'auto' }}>
                标记完成
              </Button>
            </div>
          ))}
          {done.map((f) => (
            <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 4px', borderBottom: '1px solid var(--border)' }}>
              <Tag size="small">已完成</Tag>
              <span style={{ color: 'var(--text-3)' }}>{f.plan}</span>
            </div>
          ))}
        </div>
      </AsyncState>
    </Card>
  )
}

export default function MemoryPage() {
  const patientsQuery = useQuery({ queryKey: ['patients'], queryFn: patientApi.list })
  const patients = patientsQuery.data ?? []
  const [patientId, setPatientId] = useState('')

  const keyOf = (p: PatientItem) => String(p.id)
  const activeId = patients.some((p) => keyOf(p) === patientId)
    ? patientId
    : patients.length
      ? keyOf(patients[0])
      : ''

  return (
    <PageContainer title="健康档案">
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 13, color: 'var(--text-3)' }}>选择患者</span>
        <Select
          value={activeId}
          onChange={setPatientId}
          style={{ width: 240 }}
          placeholder="选择患者"
        >
          {patients.map((p) => (
            <Select.Option key={keyOf(p)} value={keyOf(p)}>
              {p.name || `患者 #${p.id}`}
            </Select.Option>
          ))}
        </Select>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
          对话中提到的用药/过敏变化会以「提议」形式出现在这里，确认后才写入档案
        </span>
      </div>

      {patientsQuery.isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="care-skeleton-bar" style={{ height: 80 }} />
          <div className="care-skeleton-bar" style={{ height: 160 }} />
        </div>
      ) : !activeId ? (
        <EmptyState onExample={undefined} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 900 }}>
          <ProposalsCard patientId={activeId} />
          <MedicationSection patientId={activeId} />
          <AllergySection patientId={activeId} />
          <FollowupSection patientId={activeId} />
        </div>
      )}
    </PageContainer>
  )
}
