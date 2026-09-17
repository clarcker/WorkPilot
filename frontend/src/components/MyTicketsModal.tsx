/**
 * MyTicketsModal — 员工查看自己的 IT 工单
 */
import { useEffect, useState, useCallback } from 'react'
import { Modal, Table, Tag, Button, Empty, message as antMsg } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import client from '../api/client'

interface Ticket {
  id: number
  ticket_no: string
  issue_type: string
  description: string
  status: string
  created_at: string
}

const ST: Record<string, { label: string; color: string }> = {
  open:       { label: '待处理', color: 'processing' },
  in_progress:{ label: '处理中', color: 'warning' },
  closed:     { label: '已关闭', color: 'success' },
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function MyTicketsModal({ open, onClose }: Props) {
  const [items, setItems] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await client.get<Ticket[]>('/tickets/mine')
      setItems(data ?? [])
    } catch {
      antMsg.error('加载工单失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const cols = [
    { title: '工单号', dataIndex: 'ticket_no', key: 'no', width: 180 },
    { title: '类型', dataIndex: 'issue_type', key: 't', width: 110 },
    { title: '描述', dataIndex: 'description', key: 'd', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 's', width: 90,
      render: (v: string) => {
        const m = ST[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'at', width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '—'),
    },
  ]

  return (
    <Modal title="我的 IT 工单" open={open} onCancel={onClose} footer={null} width={700}>
      <Button icon={<ReloadOutlined />} onClick={load} loading={loading} style={{ marginBottom: 12 }}>
        刷新
      </Button>
      {items.length === 0 && !loading ? (
        <Empty description="暂无工单，可在对话中让我帮你报修" />
      ) : (
        <Table
          dataSource={items}
          columns={cols}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={false}
        />
      )}
    </Modal>
  )
}
