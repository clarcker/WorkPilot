/**
 * AuditLogsTab — 审计日志
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Input, Typography, message as antMsg,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { listAuditLogs, type AuditLogItem } from '../../api/admin'

const { Title } = Typography

const ACTION_LABELS: Record<string, string> = {
  'auth.login':              '用户登录',
  'auth.logout':             '用户登出',
  'auth.change_password':    '修改密码',
  'user.create':             '创建用户',
  'user.update':             '修改用户',
  'user.reset_password':     '重置密码',
  'user.disable':            '禁用账号',
  'user.enable':             '启用账号',
  'user.unlock':             '解锁账号',
  'dept.create':             '创建部门',
  'dept.update':             '修改部门',
  'dept.delete':             '删除部门',
  'doc.upload':              '上传文档',
  'doc.update':              '修改文档',
  'doc.archive':             '归档文档',
  'doc.permission_update':   '修改文档权限',
  'system.config_update':    '系统配置变更',
}

export default function AuditLogsTab() {
  const [logs, setLogs]       = useState<AuditLogItem[]>([])
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(1)
  const [loading, setLoading] = useState(false)
  const [filterAction, setFilterAction] = useState('')
  const [filterOperator, setFilterOperator] = useState('')

  const load = useCallback(async (p = page, action = filterAction, op = filterOperator) => {
    setLoading(true)
    try {
      const res = await listAuditLogs({
        page: p, page_size: 20,
        action: action || undefined,
        operator_name: op || undefined,
      })
      setLogs(res.items)
      setTotal(res.total)
    } catch { antMsg.error('加载审计日志失败') }
    finally { setLoading(false) }
  }, [page, filterAction, filterOperator])

  useEffect(() => { load() }, [load])

  const cols = [
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    { title: '操作人', dataIndex: 'operator_name', key: 'operator_name', width: 100 },
    { title: '操作类型', dataIndex: 'action', key: 'action', width: 140,
      render: (v: string) => <Tag color="blue">{ACTION_LABELS[v] ?? v}</Tag> },
    { title: '资源类型', dataIndex: 'resource_type', key: 'resource_type', width: 100,
      render: (v: string | null) => v ?? '—' },
    { title: '资源 ID', dataIndex: 'resource_id', key: 'resource_id', width: 80,
      render: (v: string | null) => v ?? '—' },
    { title: '结果', dataIndex: 'result', key: 'result', width: 80,
      render: (v: string) =>
        <Tag color={v === 'success' ? 'green' : 'red'}>{v === 'success' ? '成功' : '失败'}</Tag> },
    { title: 'IP 地址', dataIndex: 'ip_address', key: 'ip_address', width: 130,
      render: (v: string | null) => v ?? '—' },
    { title: '备注', dataIndex: 'detail', key: 'detail', ellipsis: true,
      render: (v: string | null) => v ?? '—' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12 }}>
        <Title level={5} style={{ margin: 0 }}>审计日志</Title>
        <Space>
          <Input.Search
            placeholder="操作类型（如 doc.upload）"
            allowClear
            style={{ width: 200 }}
            onSearch={(v) => { setFilterAction(v); setPage(1); load(1, v, filterOperator) }}
          />
          <Input.Search
            placeholder="操作人姓名"
            allowClear
            style={{ width: 160 }}
            onSearch={(v) => { setFilterOperator(v); setPage(1); load(1, filterAction, v) }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
        </Space>
      </div>
      <Table
        dataSource={logs} columns={cols} rowKey="id" loading={loading} size="small"
        pagination={{
          current: page, pageSize: 20, total,
          onChange: (p) => { setPage(p); load(p) },
          showTotal: (t) => `共 ${t} 条`,
        }}
        scroll={{ x: 900 }}
      />
    </div>
  )
}
