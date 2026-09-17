/**
 * TicketsTab — IT 工单处理（管理员）
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Typography, message as antMsg,
  Modal, Input, Select, Descriptions,
} from 'antd'
import { ReloadOutlined, ToolOutlined } from '@ant-design/icons'
import { listAdminTickets, updateTicket, type AdminTicket } from '../../api/admin'

const { Title, Text } = Typography

const ST: Record<string, { label: string; color: string }> = {
  open:        { label: '待处理', color: 'processing' },
  in_progress: { label: '处理中', color: 'warning' },
  closed:      { label: '已关闭', color: 'success' },
}

export default function TicketsTab() {
  const [items, setItems] = useState<AdminTicket[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState<string | undefined>()
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<AdminTicket | null>(null)
  const [status, setStatus] = useState<string>('in_progress')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async (p = page, st = filter) => {
    setLoading(true)
    try {
      const res = await listAdminTickets(p, 20, st)
      setItems(res.items)
      setTotal(res.total)
    } catch {
      antMsg.error('加载工单失败')
    } finally {
      setLoading(false)
    }
  }, [page, filter])

  useEffect(() => { load() }, [load])

  async function handleSave() {
    if (!detail) return
    setSaving(true)
    try {
      await updateTicket(detail.id, status as 'open' | 'in_progress' | 'closed', note || undefined)
      antMsg.success('工单已更新')
      setDetail(null)
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail?.message
      antMsg.error(msg || '更新失败')
    } finally {
      setSaving(false)
    }
  }

  const cols = [
    { title: '工单号', dataIndex: 'ticket_no', key: 'no', width: 180 },
    { title: '提交人', dataIndex: 'user_name', key: 'u', width: 90 },
    { title: '类型', dataIndex: 'issue_type', key: 't', width: 100 },
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
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '', key: 'op', width: 90,
      render: (_: unknown, r: AdminTicket) => (
        <Button
          size="small"
          icon={<ToolOutlined />}
          onClick={() => {
            setDetail(r)
            setStatus(r.status === 'open' ? 'in_progress' : r.status)
            setNote(r.handle_note || '')
          }}
        >
          处理
        </Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12 }}>
        <Title level={5} style={{ margin: 0 }}>
          IT 工单处理
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 13 }}>共 {total}</Text>
        </Title>
        <Space>
          <Select
            allowClear
            placeholder="按状态"
            style={{ width: 120 }}
            value={filter}
            onChange={(v) => { setFilter(v); setPage(1); load(1, v) }}
            options={[
              { value: 'open', label: '待处理' },
              { value: 'in_progress', label: '处理中' },
              { value: 'closed', label: '已关闭' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load(1)}>刷新</Button>
        </Space>
      </div>

      <Table
        dataSource={items}
        columns={cols}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{
          current: page, pageSize: 20, total,
          onChange: (p) => { setPage(p); load(p) },
        }}
      />

      <Modal
        title={`处理 ${detail?.ticket_no ?? ''}`}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={520}
      >
        {detail && (
          <>
            <Descriptions size="small" column={1} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="提交人">{detail.user_name}</Descriptions.Item>
              <Descriptions.Item label="类型">{detail.issue_type}</Descriptions.Item>
              <Descriptions.Item label="描述">{detail.description}</Descriptions.Item>
            </Descriptions>
            <Select
              style={{ width: '100%', marginBottom: 8 }}
              value={status}
              onChange={setStatus}
              options={[
                { value: 'open', label: '待处理' },
                { value: 'in_progress', label: '处理中' },
                { value: 'closed', label: '已关闭' },
              ]}
            />
            <Input.TextArea
              rows={3}
              placeholder="处理备注（关闭时建议填写）"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              style={{ marginBottom: 12 }}
            />
            <Space>
              <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
              <Button onClick={() => setDetail(null)}>取消</Button>
            </Space>
          </>
        )}
      </Modal>
    </div>
  )
}
