/**
 * 管理后台 — 部门 / 账号 / 文档 / 审批 / Trace / 审计 / 日志 / 设置
 * 访问权限：dept_admin 或 super_admin
 */
import { useState } from 'react'
import { Layout, Menu, Button, Tag, Typography } from 'antd'
import {
  ArrowLeftOutlined, BankOutlined, TeamOutlined, FileTextOutlined,
  AuditOutlined, SettingOutlined, FileSearchOutlined,
  SafetyCertificateOutlined, NodeIndexOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getStoredUser } from '../hooks/useAuth'
import DepartmentsTab from './admin/DepartmentsTab'
import UsersTab from './admin/UsersTab'
import DocumentsTab from './admin/DocumentsTab'
import ApprovalsTab from './admin/ApprovalsTab'
import TracesTab from './admin/TracesTab'
import AuditLogsTab from './admin/AuditLogsTab'
import SystemSettingsTab from './admin/SystemSettingsTab'
import SystemLogsTab from './admin/SystemLogsTab'

const { Sider, Content } = Layout
const { Text } = Typography

type TabKey =
  | 'departments' | 'users' | 'documents'
  | 'approvals' | 'traces'
  | 'audit' | 'settings' | 'logs'

export default function Admin() {
  const navigate = useNavigate()
  const currentUser = getStoredUser()
  const isSuperAdmin = currentUser?.role === 'super_admin'
  const [activeTab, setActiveTab] = useState<TabKey>(isSuperAdmin ? 'departments' : 'users')

  const menuItems = [
    ...(isSuperAdmin ? [{ key: 'departments', icon: <BankOutlined />,    label: '部门管理' }] : []),
    { key: 'users',      icon: <TeamOutlined />,      label: '账号管理' },
    { key: 'documents',  icon: <FileTextOutlined />,  label: '文档管理' },
    { key: 'approvals',  icon: <SafetyCertificateOutlined />, label: '报销审批' },
    { key: 'traces',     icon: <NodeIndexOutlined />, label: 'Agent Trace' },
    ...(isSuperAdmin ? [
      { key: 'audit',    icon: <AuditOutlined />,    label: '审计日志' },
      { key: 'logs',     icon: <FileSearchOutlined />, label: '系统日志' },
      { key: 'settings', icon: <SettingOutlined />,  label: '系统设置' },
    ] : []),
  ]

  const tabContent: Record<TabKey, React.ReactNode> = {
    departments: <DepartmentsTab />,
    users:       <UsersTab />,
    documents:   <DocumentsTab />,
    approvals:   <ApprovalsTab />,
    traces:      <TracesTab />,
    audit:       <AuditLogsTab />,
    logs:        <SystemLogsTab />,
    settings:    <SystemSettingsTab />,
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider width={200} theme="light" style={{ borderRight: '1px solid #f0f0f0', flexShrink: 0 }}>
        <div style={{ padding: '14px 16px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button size="small" type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/')} />
          <span style={{ fontWeight: 700, fontSize: 15 }}>管理后台</span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[activeTab]}
          items={menuItems}
          onClick={({ key }) => setActiveTab(key as TabKey)}
          style={{ borderRight: 0, marginTop: 8 }}
        />
        <div style={{ position: 'absolute', bottom: 0, width: '100%', padding: '12px 16px', borderTop: '1px solid #f0f0f0' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>{currentUser?.display_name}</Text>
          <br />
          <Tag color={isSuperAdmin ? 'gold' : 'blue'} style={{ marginTop: 4 }}>
            {isSuperAdmin ? '超级管理员' : '部门管理员'}
          </Tag>
        </div>
      </Sider>
      <Content style={{ padding: 24, overflow: 'auto', background: '#f5f5f5' }}>
        <div style={{ background: '#fff', borderRadius: 8, padding: 24, minHeight: '100%' }}>
          {tabContent[activeTab]}
        </div>
      </Content>
    </Layout>
  )
}
