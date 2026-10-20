/**
 * EvalTab — 评测管理（超管）：Case 列表 / 触发运行 / 运行历史 / Diff
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Modal, Form, Input, Select, Typography,
  message as antMsg, Popconfirm, Switch, Badge, Descriptions, Alert,
} from 'antd'
import { PlayCircleOutlined, PlusOutlined, ReloadOutlined, DiffOutlined } from '@ant-design/icons'
import {
  listEvalCases, getEvalCase, createEvalCase, updateEvalCase, seedEvalCases,
  triggerEvalRun, listEvalRuns, getEvalRun, diffEvalRuns, listEvalCaseGroups,
  type EvalCaseItem, type EvalRunItem, type EvalRunDetail, type EvalDiffResult,
} from '../../api/admin'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

interface DiffItem {
  case_id: string
  question?: string
  group?: string
  a_passed?: boolean
  b_passed?: boolean
}

interface JudgeCaseRow {
  case_id: string
  question?: string
  group?: string
  answer_preview?: string
  judge?: {
    faithfulness?: number
    points_covered?: string
    hallucinated_claims?: string[]
    citation_correct?: boolean
    error?: string
  }
}

const GROUP_COLORS: Record<string, string> = {
  policy: 'blue', tool: 'geekblue', multiturn: 'purple', permission: 'volcano',
  chitchat: 'green', keyword: 'cyan', distractor: 'orange',
  'distractor-lifecycle': 'orange', 'distractor-topic': 'gold',
  historical: 'magenta', gap: 'lime',
}

export default function EvalTab() {
  const [cases, setCases] = useState<EvalCaseItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [group, setGroup] = useState<string | undefined>()
  const [groups, setGroups] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [runs, setRuns] = useState<EvalRunItem[]>([])
  const [runOpen, setRunOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<EvalCaseItem | null>(null)
  const [detail, setDetail] = useState<EvalRunDetail | null>(null)
  const [caseDetail, setCaseDetail] = useState<EvalCaseItem | null>(null)
  const [diffA, setDiffA] = useState<number | undefined>()
  const [diffB, setDiffB] = useState<number | undefined>()
  const [diffResult, setDiffResult] = useState<EvalDiffResult | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [pollId, setPollId] = useState<number | null>(null)
  const [runForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const loadCases = useCallback(async (p = page, g = group) => {
    setLoading(true)
    try {
      const res = await listEvalCases({ page: p, page_size: 20, group: g })
      setCases(res.items)
      setTotal(res.total)
    } catch { antMsg.error('加载 case 失败') }
    finally { setLoading(false) }
  }, [page, group])

  const loadRuns = useCallback(async () => {
    try { setRuns(await listEvalRuns()) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    loadCases()
    loadRuns()
    listEvalCaseGroups().then(setGroups).catch(() => {})
  }, [loadCases, loadRuns])

  // 轮询进行中的 judge 运行
  useEffect(() => {
    if (!pollId) return
    const t = setInterval(async () => {
      try {
        const d = await getEvalRun(pollId)
        setDetail(d)
        if (d.status === 'finished' || d.status === 'failed') {
          setPollId(null)
          loadRuns()
          antMsg.success(d.status === 'finished' ? `评测完成 run #${d.id}` : '评测失败')
        }
      } catch { /* ignore */ }
    }, 4000)
    return () => clearInterval(t)
  }, [pollId, loadRuns])

  async function handleTrigger() {
    const vals = await runForm.validateFields()
    setTriggering(true)
    try {
      const res = await triggerEvalRun({
        mode: vals.mode || 'fast',
        label: vals.label,
        skip_generation: vals.mode === 'judge' ? false : vals.skip_generation !== false,
        tool_dry_run: vals.tool_dry_run !== false,
      })
      if (res.run_id && res.mode === 'judge') {
        antMsg.success(`judge 已启动 run #${res.run_id}`)
        setPollId(res.run_id)
        setRunOpen(false)
      } else if (res.run_id != null || res.total_cases != null) {
        const rid = res.run_id
        antMsg.success('评测完成')
        setRunOpen(false)
        loadRuns()
        if (typeof rid === 'number') {
          const d = await getEvalRun(rid)
          setDetail(d)
        }
      } else {
        antMsg.success('评测已触发')
        setRunOpen(false)
        loadRuns()
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } | string } } })?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message ?? '触发失败')
    } finally { setTriggering(false) }
  }

  async function openEdit(row: EvalCaseItem | null) {
    setEditing(row)
    if (row) {
      const full = await getEvalCase(row.case_id)
      editForm.setFieldsValue({
        case_id: full.case_id,
        question: full.question,
        group: full.group,
        payload: JSON.stringify(full.payload ?? {}, null, 2),
        active: full.active !== false,
      })
    } else {
      editForm.resetFields()
      editForm.setFieldsValue({ active: true, payload: '{\n  "expected_intent": "rag"\n}' })
    }
    setEditOpen(true)
  }

  async function handleSaveCase() {
    const vals = await editForm.validateFields()
    let payload: Record<string, unknown>
    try { payload = JSON.parse(vals.payload || '{}') }
    catch { antMsg.error('payload 不是合法 JSON'); return }
    try {
      if (editing) {
        await updateEvalCase(editing.case_id, {
          question: vals.question,
          group: vals.group,
          payload,
          active: vals.active,
        })
        antMsg.success('已更新')
      } else {
        await createEvalCase({
          case_id: vals.case_id || undefined,
          question: vals.question,
          group: vals.group,
          payload,
          active: vals.active,
        })
        antMsg.success('已创建')
      }
      setEditOpen(false)
      loadCases()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } | string } } })?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message ?? '保存失败')
    }
  }

  async function handleDiff() {
    if (!diffA || !diffB) { antMsg.warning('请选择两次运行'); return }
    try {
      const d = await diffEvalRuns(diffB, diffA) // a=较新, other=较旧 → became_pass 相对 other→a
      setDiffResult(d)
    } catch { antMsg.error('对比失败') }
  }

  async function openRunDetail(id: number) {
    try {
      const d = await getEvalRun(id)
      setDetail(d)
    } catch { antMsg.error('加载 run 失败') }
  }

  async function openCaseDetail(caseId: string) {
    try {
      const d = await getEvalCase(caseId)
      setCaseDetail(d)
    } catch { antMsg.error('加载 case 失败') }
  }

  const caseCols = [
    { title: 'ID', dataIndex: 'case_id', key: 'case_id', width: 90 },
    { title: '问题', dataIndex: 'question', key: 'question', ellipsis: true },
    {
      title: '分组', dataIndex: 'group', key: 'group', width: 140,
      render: (v: string) => v ? <Tag color={GROUP_COLORS[v] || 'default'}>{v}</Tag> : '—',
    },
    {
      title: '来源', dataIndex: 'source', key: 'source', width: 80,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '启用', dataIndex: 'active', key: 'active', width: 70,
      render: (v: boolean, row: EvalCaseItem) => (
        <Switch
          size="small"
          checked={v !== false}
          onChange={async (checked) => {
            await updateEvalCase(row.case_id, { active: checked })
            loadCases()
          }}
        />
      ),
    },
    {
      title: '操作', key: 'op', width: 140,
      render: (_: unknown, row: EvalCaseItem) => (
        <Space>
          <Button size="small" onClick={() => openEdit(row)}>编辑</Button>
          <Button size="small" onClick={() => openCaseDetail(row.case_id)}>详情</Button>
        </Space>
      ),
    },
  ]

  const runCols = [
    { title: 'Run', dataIndex: 'id', key: 'id', width: 60 },
    { title: '模式', dataIndex: 'mode', key: 'mode', width: 70,
      render: (v: string) => <Tag color={v === 'judge' ? 'purple' : 'blue'}>{v || 'fast'}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string, r: EvalRunItem) => (
        <Badge
          status={v === 'finished' ? 'success' : v === 'failed' ? 'error' : 'processing'}
          text={`${v || 'finished'}${r.progress != null && v === 'running' ? ` ${r.progress}/${r.total_cases}` : ''}`}
        />
      )},
    { title: 'label', dataIndex: 'label', key: 'label', width: 120,
      render: (v: string | null) => v || '—' },
    { title: 'doc_hit', dataIndex: 'doc_hit_rate', key: 'doc_hit', width: 80,
      render: (v: number | null) => v != null ? v.toFixed(3) : '—' },
    { title: 'mrr', dataIndex: 'mrr', key: 'mrr', width: 70,
      render: (v: number | null) => v != null ? v.toFixed(3) : '—' },
    { title: 'faith', dataIndex: 'faithfulness_avg', key: 'faith', width: 70,
      render: (v: number | null) => v != null ? v.toFixed(2) : '—' },
    { title: 'hallu', dataIndex: 'hallucination_count', key: 'hallu', width: 70,
      render: (v: number | null) => v ?? '—' },
    {
      title: '操作', key: 'op', width: 80,
      render: (_: unknown, r: EvalRunItem) => (
        <Button size="small" onClick={() => openRunDetail(r.id)}>查看</Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={5} style={{ margin: 0 }}>评测管理</Title>
        <Space wrap>
          <Select
            allowClear placeholder="分组" style={{ width: 160 }} value={group}
            onChange={(v) => { setGroup(v); setPage(1); loadCases(1, v) }}
            options={groups.map(g => ({ value: g, label: g }))}
          />
          <Button icon={<ReloadOutlined />} onClick={() => { loadCases(); loadRuns() }}>刷新</Button>
          <Popconfirm title="从 cases.json 覆盖导入 eval_cases？" onConfirm={async () => {
            const r = await seedEvalCases(); antMsg.success(`导入 ${r.imported} 条`); loadCases()
          }}>
            <Button>导入 JSON</Button>
          </Popconfirm>
          <Button icon={<PlusOutlined />} onClick={() => openEdit(null)}>新建 Case</Button>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setRunOpen(true)}>运行评测</Button>
        </Space>
      </div>

      <Title level={5} style={{ marginTop: 8 }}>Case 列表</Title>
      <Table
        dataSource={cases} columns={caseCols} rowKey="case_id" loading={loading} size="small"
        pagination={{ current: page, pageSize: 20, total, onChange: (p) => { setPage(p); loadCases(p) }, showTotal: (t) => `${t} 条` }}
      />

      <Title level={5} style={{ marginTop: 24 }}>运行历史</Title>
      <Space style={{ marginBottom: 8 }} wrap>
        <Select allowClear placeholder="Run A（较新）" style={{ width: 140 }} value={diffA} onChange={setDiffA}
          options={runs.map(r => ({ value: r.id, label: `#${r.id} ${r.label || r.mode || ''}` }))} />
        <Select allowClear placeholder="Run B（较旧）" style={{ width: 140 }} value={diffB} onChange={setDiffB}
          options={runs.map(r => ({ value: r.id, label: `#${r.id} ${r.label || r.mode || ''}` }))} />
        <Button icon={<DiffOutlined />} onClick={handleDiff}>对比 Diff</Button>
      </Space>
      <Table dataSource={runs} columns={runCols} rowKey="id" size="small" pagination={false} />

      {diffResult && (
        <div style={{ marginTop: 16 }}>
          <Alert
            type="info"
            message={`Diff：run #${diffResult.run_a?.id} vs #${diffResult.run_b?.id}`}
            description={
              <Space direction="vertical" size={4}>
                <Text>通过←失败：{diffResult.became_pass?.length || 0} · 失败←通过：{diffResult.became_fail?.length || 0} · 仍失败：{diffResult.still_fail?.length || 0}</Text>
                <Text type="secondary">
                  {Object.entries(diffResult.by_group || {}).map(([g, v]) =>
                    `${g}: +${v.became_pass}/-${v.became_fail}/still ${v.still_fail}`).join(' · ') || '—'}
                </Text>
                {((diffResult.became_fail || []) as DiffItem[]).slice(0, 8).map(i => (
                  <Text key={i.case_id} type="danger" style={{ fontSize: 12 }}>
                    退化 {i.case_id}: {i.question || ''}
                  </Text>
                ))}
                {((diffResult.became_pass || []) as DiffItem[]).slice(0, 8).map(i => (
                  <Text key={i.case_id} type="success" style={{ fontSize: 12 }}>
                    修复 {i.case_id}: {i.question || ''}
                  </Text>
                ))}
              </Space>
            }
          />
        </div>
      )}

      {detail && (
        <Modal
          title={`Run #${detail.id} · ${detail.mode || 'fast'} · ${detail.status || ''}`}
          open={!!detail} onCancel={() => setDetail(null)} footer={null} width={720}
        >
          <Descriptions size="small" column={3} bordered>
            <Descriptions.Item label="label">{detail.label || '—'}</Descriptions.Item>
            <Descriptions.Item label="进度">{detail.progress ?? '—'} / {detail.total_cases ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="doc_hit">{detail.metrics?.doc_hit_rate?.toFixed?.(3) ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="mrr">{detail.metrics?.mrr?.toFixed?.(3) ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="faithfulness">{detail.faithfulness_avg?.toFixed?.(2) ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="points">{detail.points_coverage?.toFixed?.(3) ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="hallucination">{detail.hallucination_count ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="judge_model">{detail.judge_model || '—'}</Descriptions.Item>
            <Descriptions.Item label="note">{detail.note || '—'}</Descriptions.Item>
          </Descriptions>
          {detail.judge_cases && detail.judge_cases.length > 0 && (
            <>
              <Title level={5} style={{ marginTop: 16 }}>Judge 明细</Title>
              {(detail.judge_cases as JudgeCaseRow[]).map(j => (
                <Paragraph key={j.case_id} style={{ marginBottom: 8, fontSize: 12 }}>
                  <Tag>{j.case_id}</Tag>
                  {j.question || ''}
                  <br />
                  faith={j.judge?.faithfulness ?? '—'} points={j.judge?.points_covered ?? '—'}
                  {j.judge?.hallucinated_claims?.length ? (
                    <> · 编造：{j.judge.hallucinated_claims.join('；')}</>
                  ) : null}
                  <br />
                  <Text type="secondary">{j.answer_preview || ''}</Text>
                </Paragraph>
              ))}
            </>
          )}
        </Modal>
      )}

      {caseDetail && (
        <Modal
          title={`Case ${caseDetail.case_id}`} open={!!caseDetail}
          onCancel={() => setCaseDetail(null)} footer={null} width={640}
        >
          <Paragraph>{caseDetail.question}</Paragraph>
          <Paragraph>
            <Tag>{caseDetail.group || '—'}</Tag>
            <Tag>{caseDetail.source}</Tag>
            {Boolean((caseDetail.payload as Record<string, unknown>)?.judge) && <Tag color="purple">judge</Tag>}
          </Paragraph>
          <Paragraph>
            <pre style={{ maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(caseDetail.payload, null, 2)}
            </pre>
          </Paragraph>
          {caseDetail.last_run?.result && (
            <>
              <Title level={5}>最近一次结果（run #{caseDetail.last_run.run_id}）</Title>
              <Paragraph>
                <pre style={{ maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {JSON.stringify(caseDetail.last_run.result, null, 2)}
                </pre>
              </Paragraph>
            </>
          )}
        </Modal>
      )}

      <Modal
        title="运行评测" open={runOpen} onOk={handleTrigger} onCancel={() => setRunOpen(false)}
        confirmLoading={triggering} okText="启动"
      >
        <Form form={runForm} layout="vertical">
          <Form.Item name="mode" label="模式" initialValue="fast">
            <Select options={[
              { value: 'fast', label: '快速（skip_generation，检索/工具指标）' },
              { value: 'judge', label: 'Judge（生成 + LLM-as-judge，约数分钟）' },
            ]} />
          </Form.Item>
          <Form.Item name="label" label="Label（可选）">
            <Input placeholder="如 Q4-smoke / Q3-fix" maxLength={100} />
          </Form.Item>
          <Form.Item name="skip_generation" label="跳过生成（fast 模式）" initialValue={true} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="tool_dry_run" label="工具演练（不写库）" initialValue={true} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editing ? `编辑 ${editing.case_id}` : '新建 Case'}
        open={editOpen} onOk={handleSaveCase} onCancel={() => setEditOpen(false)} okText="保存" width={640}
      >
        <Form form={editForm} layout="vertical">
          {!editing && (
            <Form.Item name="case_id" label="Case ID（可空，自动编号）">
              <Input placeholder="case_083" />
            </Form.Item>
          )}
          <Form.Item name="question" label="问题" rules={[{ required: true }]}>
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="group" label="分组">
            <Select allowClear options={groups.map(g => ({ value: g, label: g }))} />
          </Form.Item>
          <Form.Item name="payload" label="Payload JSON" rules={[{ required: true }]}>
            <TextArea rows={10} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="active" label="启用" valuePropName="checked" initialValue>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
