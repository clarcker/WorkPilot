/**
 * ConfirmCard — 写操作人工确认卡（报销草稿等）
 * SSE confirm_required 时渲染；确认/取消调用报销 API。
 */
import { useState } from 'react'
import { Card, Button, Space, Typography, Tag, message as antMsg, Descriptions } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  AuditOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { confirmReimbursement, cancelReimbursement } from '../api/reimbursements'
import type { ConfirmRequiredPayload } from '../types'

const { Text } = Typography

const SLOT_LABELS: Record<string, string> = {
  days: '天数',
  trip_start: '出差开始日期',
  trip_end: '出差结束日期',
  approval_ref: '出差审批单号',
  category: '报销类别',
  amount: '金额',
}

interface Props {
  data: ConfirmRequiredPayload
  onDone?: (action: 'confirmed' | 'cancelled', msg: string) => void
}

export default function ConfirmCard({ data, onDone }: Props) {
  const [loading, setLoading] = useState<'confirm' | 'cancel' | null>(null)
  const [resolved, setResolved] = useState<'confirmed' | 'cancelled' | null>(null)

  const p = data.payload || {}
  const form = p.form || {}
  const pre = p.precheck || {}
  const requestId = p.request_id

  async function handleConfirm() {
    if (!requestId) return
    setLoading('confirm')
    try {
      const res = await confirmReimbursement(requestId)
      antMsg.success(res.message || '已提交')
      setResolved('confirmed')
      onDone?.('confirmed', res.message || '已确认提交')
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: { message?: string } | string } } })
          ?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message || '确认失败')
    } finally {
      setLoading(null)
    }
  }

  async function handleCancel() {
    if (!requestId) return
    setLoading('cancel')
    try {
      const res = await cancelReimbursement(requestId)
      antMsg.success(res.message || '已取消')
      setResolved('cancelled')
      onDone?.('cancelled', res.message || '已取消')
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: { message?: string } | string } } })
          ?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message || '取消失败')
    } finally {
      setLoading(null)
    }
  }

  if (resolved) {
    return (
      <Card size="small" style={{ margin: '8px 0', background: resolved === 'confirmed' ? '#f6ffed' : '#fafafa' }}>
        <Space>
          {resolved === 'confirmed' ? (
            <CheckCircleOutlined style={{ color: '#52c41a' }} />
          ) : (
            <CloseCircleOutlined style={{ color: '#999' }} />
          )}
          <Text type="secondary">
            {resolved === 'confirmed'
              ? `申请单 ${p.request_no ?? ''} 已提交，等待部门审批`
              : `申请单 ${p.request_no ?? ''} 已取消`}
          </Text>
        </Space>
      </Card>
    )
  }

  const over = (pre.violations || []).filter((v) => v.rule === 'daily_max')

  return (
    <Card
      size="small"
      style={{
        margin: '8px 0',
        background: '#fffbe6',
        border: '1px solid #ffe58f',
      }}
      title={
        <Space>
          <AuditOutlined style={{ color: '#faad14' }} />
          <span>请确认提交报销申请</span>
          {p.request_no && <Tag color="gold">{p.request_no}</Tag>}
        </Space>
      }
    >
      <Descriptions size="small" column={2} style={{ marginBottom: 8 }}>
        <Descriptions.Item label="类别">{form.category ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="金额">
          <Text strong>{form.amount != null ? `${form.amount} 元` : '—'}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="天数">{form.days ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="出差日期">
          {[form.trip_start, form.trip_end].filter(Boolean).join(' ~ ') || '—'}
        </Descriptions.Item>
        {form.approval_ref && (
          <Descriptions.Item label="关联审批单" span={2}>
            {form.approval_ref}
          </Descriptions.Item>
        )}
        {pre.remaining != null && (
          <Descriptions.Item label="年度剩余" span={2}>
            {pre.remaining} 元
          </Descriptions.Item>
        )}
      </Descriptions>

      {pre.requires_special_approval && (
        <div style={{ marginBottom: 8 }}>
          {over.map((v, i) => (
            <div key={i} style={{ color: '#d46b08', fontSize: 12, marginBottom: 4 }}>
              <WarningOutlined /> {v.message}
              {v.over_amount != null && `（超标 ${v.over_amount} 元）`}
            </div>
          ))}
          <Tag color="orange">提交后将走部门负责人特批流程</Tag>
        </div>
      )}

      <Space>
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          loading={loading === 'confirm'}
          onClick={handleConfirm}
        >
          确认提交
        </Button>
        <Button
          danger
          icon={<CloseCircleOutlined />}
          loading={loading === 'cancel'}
          onClick={handleCancel}
        >
          取消
        </Button>
      </Space>
      <div style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          确认前不会进入审批流；取消不产生任何记录。
        </Text>
      </div>
    </Card>
  )
}

/** 槽位缺失提示条 */
export function FormIncompleteBanner({ slots, message }: { slots: string[]; message?: string }) {
  const labels = slots.map((s) => SLOT_LABELS[s] || s).join('、')
  return (
    <Card
      size="small"
      style={{ margin: '8px 0', background: '#e6f4ff', border: '1px solid #91caff' }}
    >
      <Space>
        <WarningOutlined style={{ color: '#1677ff' }} />
        <Text>
          {message || `请补充：${labels}`}
          {slots.length > 0 && !message && (
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              缺少字段：{labels}
            </Text>
          )}
        </Text>
      </Space>
    </Card>
  )
}
