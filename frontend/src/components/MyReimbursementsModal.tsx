/**
 * MyReimbursementsModal — 员工查看自己的报销申请与进度
 * 所有登录用户可从聊天侧栏打开。
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Modal, Table, Tag, Typography, Button, Space, message as antMsg, Empty, Alert,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { listMyReimbursements, type ReimbSummary } from '../api/reimbursements'

const { Text } = Typography

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft:    { label: '待确认', color: 'gold' },
  pending:  { label: '待审批', color: 'processing' },
  approved: { label: '已批准', color: 'success' },
  rejected: { label: '已驳回', color: 'error' },
  cancelled:{ label: '已取消', color: 'default' },
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function MyReimbursementsModal({ open, onClose }: Props) {
  const [items, setItems] = useState<ReimbSummary[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setItems(await listMyReimbursements())
    } catch {
      antMsg.error('加载我的报销失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const cols = [
    { title: '单号', dataIndex: 'request_no', key: 'no', width: 150 },
    { title: '类别', dataIndex: 'category', key: 'cat', width: 100 },
    {
      title: '金额', dataIndex: 'amount', key: 'amt', width: 90,
      render: (v: number) => <Text strong>{v} 元</Text>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'st', width: 90,
      render: (v: string) => {
        const m = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '申请时间', dataIndex: 'created_at', key: 'at', width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '—'),
    },
    {
      title: '审批意见', dataIndex: 'approver_comment', key: 'cmt', ellipsis: true,
      render: (v: string | null) => v || '—',
    },
  ]

  const draftCount = items.filter((i) => i.status === 'draft').length

  return (
    <Modal
      title="我的报销申请"
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
    >
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
        {draftCount > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ padding: '4px 12px' }}
            message={`有 ${draftCount} 条待确认，回到对话中点「确认提交」后才会进入审批`}
          />
        )}
      </Space>

      {items.length === 0 && !loading ? (
        <Empty description="暂无报销记录，可在对话中让我帮你提交" />
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
