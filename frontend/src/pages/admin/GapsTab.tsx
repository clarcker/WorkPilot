/**
 * GapsTab — 知识缺口（管理员）
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Typography, message as antMsg,
  Space, Alert, Switch,
} from 'antd'
import { ReloadOutlined, CheckCircleOutlined } from '@ant-design/icons'
import client from '../../api/client'

const { Title, Text, Paragraph } = Typography

interface GapItem {
  id: number
  query: string
  intent: string | null
  top1_score: number | null
  doc_hit: boolean
  feedback: string | null
  feedback_reason: string | null
  answer_preview: string | null
  freq: number
  created_at: string
}

export default function GapsTab() {
  const [items, setItems] = useState<GapItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [showResolved, setShowResolved] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (p = page, resolved = showResolved) => {
    setLoading(true)
    try {
      const { data } = await client.get('/quality/gaps', {
        params: { page: p, page_size: 20, resolved },
      })
      setItems(data?.items ?? [])
      setTotal(data?.total ?? 0)
    } catch {
      antMsg.error('加载知识缺口失败')
    } finally {
      setLoading(false)
    }
  }, [page, showResolved])

  useEffect(() => { load() }, [load])

  async function resolve(id: number) {
    try {
      await client.post(`/quality/gaps/${id}/resolve`, { resolved: true })
      antMsg.success('已标记解决')
      load()
    } catch {
      antMsg.error('操作失败')
    }
  }

  const cols = [
    { title: '问题', dataIndex: 'query', key: 'q', ellipsis: true },
    {
      title: 'top1', dataIndex: 'top1_score', key: 's', width: 80,
      render: (v: number | null) => v != null ? v.toFixed(2) : '—',
    },
    {
      title: '反馈', dataIndex: 'feedback', key: 'f', width: 70,
      render: (v: string | null) =>
        v === 'down' ? <Tag color="red">👎</Tag> : v === 'up' ? <Tag color="green">👍</Tag> : '—',
    },
    { title: '原因', dataIndex: 'feedback_reason', key: 'r', width: 110 },
    {
      title: '频次', dataIndex: 'freq', key: 'freq', width: 60,
    },
    {
      title: '时间', dataIndex: 'created_at', key: 'at', width: 150,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '', key: 'op', width: 90,
      render: (_: unknown, r: GapItem) =>
        !showResolved ? (
          <Button size="small" icon={<CheckCircleOutlined />} onClick={() => resolve(r.id)}>
            已解决
          </Button>
        ) : null,
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>
          知识缺口
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 13 }}>{total} 条</Text>
        </Title>
        <Space>
          <Text type="secondary">已解决</Text>
          <Switch
            checked={showResolved}
            onChange={(v) => { setShowResolved(v); setPage(1); load(1, v) }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load(1)}>刷新</Button>
        </Space>
      </div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="缺口 = 检索为空 / 相似度低 / 用户点 👎 / 回答含「未找到」。补文档后可标记已解决。"
      />
      <Table
        dataSource={items}
        columns={cols}
        rowKey="id"
        loading={loading}
        size="small"
        expandable={{
          expandedRowRender: (r) => (
            <Paragraph type="secondary" style={{ margin: 0, fontSize: 12 }}>
              {r.answer_preview || '（无回答摘要）'}
            </Paragraph>
          ),
        }}
        pagination={{
          current: page, pageSize: 20, total,
          onChange: (p) => { setPage(p); load(p) },
        }}
      />
    </div>
  )
}
