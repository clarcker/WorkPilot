/**
 * TracesTab — Agent 节点级 trace（超管全部，部门管理员本部门）
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Typography, message as antMsg,
  Modal, Descriptions, Timeline, Spin, Space,
} from 'antd'
import { ReloadOutlined, NodeIndexOutlined } from '@ant-design/icons'
import { listTraces, getTrace, type AgentTraceListItem, type AgentTraceDetail } from '../../api/admin'

const { Title, Text, Paragraph } = Typography

export default function TracesTab() {
  const [items, setItems] = useState<AgentTraceListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<AgentTraceDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async (p = page) => {
    setLoading(true)
    try {
      const res = await listTraces({ page: p, page_size: 20 })
      setItems(res.items)
      setTotal(res.total)
    } catch {
      antMsg.error('加载 trace 失败')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { load() }, [load])

  async function openDetail(id: number) {
    setDetailLoading(true)
    try {
      setDetail(await getTrace(id))
    } catch {
      antMsg.error('加载详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const cols = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '问题', dataIndex: 'query', key: 'q', ellipsis: true,
      render: (v: string) => <Text style={{ fontSize: 13 }}>{v}</Text>,
    },
    {
      title: '意图', dataIndex: 'intent', key: 'intent', width: 90,
      render: (v: string | null) =>
        v ? <Tag color={v === 'rag' ? 'blue' : 'default'}>{v}</Tag> : '—',
    },
    {
      title: '节点', dataIndex: 'steps', key: 'steps', width: 80,
      render: (s: AgentTraceListItem['steps']) => s?.length ?? 0,
    },
    {
      title: '工具', dataIndex: 'tool_calls', key: 'tools', width: 80,
      render: (t: AgentTraceListItem['tool_calls']) => t?.length ?? 0,
    },
    {
      title: '模型', dataIndex: 'llm_model', key: 'model', width: 140, ellipsis: true,
      render: (v: string | null) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : '—',
    },
    {
      title: '时间', dataIndex: 'created_at', key: 'at', width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '', key: 'op', width: 80,
      render: (_: unknown, r: AgentTraceListItem) => (
        <Button size="small" icon={<NodeIndexOutlined />} onClick={() => openDetail(r.id)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>
          Agent Trace
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 13 }}>共 {total} 条</Text>
        </Title>
        <Button icon={<ReloadOutlined />} onClick={() => load(1)}>刷新</Button>
      </div>

      <Table
        dataSource={items}
        columns={cols}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{
          current: page, pageSize: 20, total,
          onChange: (p) => { setPage(p); load(p) },
        }}
      />

      <Modal
        title={detail ? `Trace #${detail.id}` : 'Trace'}
        open={!!detail || detailLoading}
        onCancel={() => setDetail(null)}
        footer={null}
        width={720}
      >
        {detailLoading || !detail ? (
          <div style={{ textAlign: 'center', padding: 32 }}><Spin /></div>
        ) : (
          <>
            <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="原始问题" span={2}>{detail.query}</Descriptions.Item>
              {detail.rewritten_query && detail.rewritten_query !== detail.query && (
                <Descriptions.Item label="改写后" span={2}>
                  {detail.rewritten_query}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="意图">{detail.intent ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="模型">{detail.llm_model ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="会话 ID">{detail.conversation_id ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="用户 ID">{detail.user_id}</Descriptions.Item>
            </Descriptions>

            <Title level={5} style={{ marginTop: 8 }}>节点</Title>
            <Timeline
              items={(detail.steps || []).map((s) => ({
                color: s.error ? 'red' : 'green',
                children: (
                  <div>
                    <Space>
                      <Text strong>{s.node}</Text>
                      {s.latency_ms != null && (
                        <Text type="secondary" style={{ fontSize: 12 }}>{s.latency_ms}ms</Text>
                      )}
                    </Space>
                    <div style={{ fontSize: 12, color: '#666' }}>{s.output_summary}</div>
                    {s.error && <Text type="danger" style={{ fontSize: 12 }}>{s.error}</Text>}
                  </div>
                ),
              }))}
            />

            {detail.tool_calls?.length ? (
              <>
                <Title level={5}>工具</Title>
                {detail.tool_calls.map((tc, i) => (
                  <Paragraph key={i} style={{ fontSize: 12, marginBottom: 4 }}>
                    <Text code>{String((tc as { name?: string }).name ?? '?')}</Text>{' '}
                    success={(tc as { success?: boolean }).success ? '是' : '否'}{' '}
                    <Text type="secondary">
                      {JSON.stringify((tc as { result?: unknown }).result ?? (tc as { error?: string }).error ?? {}).slice(0, 180)}
                    </Text>
                  </Paragraph>
                ))}
              </>
            ) : null}

            {detail.final_answer && (
              <>
                <Title level={5}>回答摘要</Title>
                <Paragraph style={{ fontSize: 13, maxHeight: 160, overflow: 'auto' }}>
                  {detail.final_answer.slice(0, 800)}
                </Paragraph>
              </>
            )}
          </>
        )}
      </Modal>
    </div>
  )
}
