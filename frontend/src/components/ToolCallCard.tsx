import { Card, Tag, Typography } from 'antd'
import {
  ToolOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import type { ToolCallInfo } from '../types'

const { Text } = Typography

const TOOL_LABELS: Record<string, string> = {
  query_employee_profile: '查询员工信息',
  query_reimbursement_limit: '查询报销额度',
  precheck_reimbursement: '报销预审',
  submit_reimbursement_request: '提交报销申请',
  query_my_reimbursements: '查询报销进度',
  create_it_ticket: '创建 IT 工单',
}

export default function ToolCallCard({ info }: { info: ToolCallInfo }) {
  const label = TOOL_LABELS[info.tool_name] || info.tool_name

  return (
    <Card
      size="small"
      style={{
        margin: '8px 0',
        background: info.allowed ? '#f6ffed' : '#fff2f0',
        border: `1px solid ${info.allowed ? '#b7eb8f' : '#ffccc7'}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <ToolOutlined />
        <Text strong>{label}</Text>
        {info.allowed ? (
          <Tag icon={<CheckCircleOutlined />} color="success">已执行</Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="error">已拒绝</Tag>
        )}
        {info.latency_ms != null && (
          <Text type="secondary" style={{ fontSize: 12 }}>{info.latency_ms}ms</Text>
        )}
      </div>

      {info.tool_args && Object.keys(info.tool_args).length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>参数: </Text>
          <Text code style={{ fontSize: 12 }}>
            {JSON.stringify(info.tool_args)}
          </Text>
        </div>
      )}

      {info.deny_reason && (
        <Text type="danger" style={{ fontSize: 12 }}>{info.deny_reason}</Text>
      )}

      {info.error && (
        <Text type="danger" style={{ fontSize: 12 }}>错误: {info.error}</Text>
      )}

      {info.allowed && info.result != null && (
        <div style={{ marginTop: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>结果: </Text>
          <Text style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
            {typeof info.result === 'string'
              ? info.result
              : JSON.stringify(info.result, null, 2)}
          </Text>
        </div>
      )}
    </Card>
  )
}
