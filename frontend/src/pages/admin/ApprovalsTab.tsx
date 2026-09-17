/**
 * ApprovalsTab — 报销审批队列（部门管理员 / 超管）
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Typography, message as antMsg,
  Modal, Input, Descriptions, Alert,
} from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { listApprovals, decideApproval, type ApprovalItem } from '../../api/admin'

const { Title, Text } = Typography

export default function ApprovalsTab() {
  const [items, setItems] = useState<ApprovalItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<ApprovalItem | null>(null)
  const [comment, setComment] = useState('')
  const [deciding, setDeciding] = useState(false)

  const load = useCallback(async (p = page) => {
    setLoading(true)
    try {
      const res = await listApprovals(p, 20)
      setItems(res.items)
      setTotal(res.total)
    } catch {
      antMsg.error('加载审批队列失败')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { load() }, [load])

  async function handleDecide(approved: boolean) {
    if (!detail) return
    setDeciding(true)
    try {
      const res = await decideApproval(detail.id, approved, comment || undefined)
      antMsg.success(approved ? `已批准 ${res.request_no}` : `已驳回 ${res.request_no}`)
      setDetail(null)
      setComment('')
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail?.message
      antMsg.error(msg || '审批失败')
    } finally {
      setDeciding(false)
    }
  }

  const cols = [
    { title: '单号', dataIndex: 'request_no', key: 'no', width: 160 },
    { title: '类别', dataIndex: 'category', key: 'cat', width: 100 },
    {
      title: '金额', dataIndex: 'amount', key: 'amt', width: 90,
      render: (v: number) => <Text strong>{v} 元</Text>,
    },
    { title: '天数', dataIndex: 'days', key: 'days', width: 70,
      render: (v: number | null) => v ?? '—' },
    {
      title: '出差日期', key: 'trip', width: 180,
      render: (_: unknown, r: ApprovalItem) =>
        [r.trip_start, r.trip_end].filter(Boolean).join(' ~ ') || '—',
    },
    {
      title: '特批', key: 'special', width: 80,
      render: (_: unknown, r: ApprovalItem) =>
        r.precheck_result?.requires_special_approval
          ? <Tag color="orange">需特批</Tag>
          : <Tag color="green">正常</Tag>,
    },
    { title: '申请时间', dataIndex: 'created_at', key: 'at', width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    {
      title: '操作', key: 'op', width: 100,
      render: (_: unknown, r: ApprovalItem) => (
        <Button size="small" type="primary" onClick={() => { setDetail(r); setComment('') }}>
          审批
        </Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>
          报销审批队列
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 13 }}>待处理 {total}</Text>
        </Title>
        <Button icon={<ReloadOutlined />} onClick={() => load(1)}>刷新</Button>
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
        title={`审批 ${detail?.request_no ?? ''}`}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={560}
      >
        {detail && (
          <>
            <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="类别">{detail.category}</Descriptions.Item>
              <Descriptions.Item label="金额">{detail.amount} 元</Descriptions.Item>
              <Descriptions.Item label="天数">{detail.days ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="关联审批单">{detail.approval_ref ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="出差" span={2}>
                {[detail.trip_start, detail.trip_end].filter(Boolean).join(' ~ ') || '—'}
              </Descriptions.Item>
              {detail.precheck_result?.remaining != null && (
                <Descriptions.Item label="年度剩余" span={2}>
                  {detail.precheck_result.remaining} 元
                </Descriptions.Item>
              )}
            </Descriptions>

            {detail.precheck_result?.violations?.length ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="预审提示"
                description={
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {detail.precheck_result.violations.map((v, i) => (
                      <li key={i}>{v.message}</li>
                    ))}
                  </ul>
                }
              />
            ) : null}

            <Input.TextArea
              rows={2}
              placeholder="审批意见（驳回时建议填写）"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              style={{ marginBottom: 12 }}
            />
            <Space>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                loading={deciding}
                onClick={() => handleDecide(true)}
              >
                批准
              </Button>
              <Button
                danger
                icon={<CloseCircleOutlined />}
                loading={deciding}
                onClick={() => handleDecide(false)}
              >
                驳回
              </Button>
              <Button onClick={() => setDetail(null)}>关闭</Button>
            </Space>
          </>
        )}
      </Modal>
    </div>
  )
}
