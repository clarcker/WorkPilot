/**
 * UsersTab — 账号管理
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Modal, Form, Input,
  Select, Tooltip, Typography, message as antMsg,
  Descriptions, Alert,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, CopyOutlined,
  LockOutlined, UnlockOutlined, StopOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import { getStoredUser } from '../../hooks/useAuth'
import {
  listDepts, listUsers, suggestUsername, suggestEmployeeNo, createUser,
  resetPassword, setUserStatus, unlockUser,
  type Dept, type AdminUser, type UserCreateResult,
} from '../../api/admin'

const { Text, Title } = Typography

export default function UsersTab() {
  const currentUser = getStoredUser()
  const isSuperAdmin = currentUser?.role === 'super_admin'

  const [users, setUsers]       = useState<AdminUser[]>([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(1)
  const [loading, setLoading]   = useState(false)
  const [keyword, setKeyword]   = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [pwdResult, setPwdResult]   = useState<{ username: string; password: string } | null>(null)
  const [depts, setDepts]       = useState<Dept[]>([])
  const [createForm] = Form.useForm()

  const load = useCallback(async (p = page, kw = keyword) => {
    setLoading(true)
    try {
      const res = await listUsers({ page: p, page_size: 20, keyword: kw || undefined })
      setUsers(res.items)
      setTotal(res.total)
    } catch { antMsg.error('加载用户列表失败') }
    finally { setLoading(false) }
  }, [page, keyword])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (isSuperAdmin) listDepts().then(setDepts).catch(() => {}) }, [isSuperAdmin])

  // ── 创建用户 ────────────────────────────────────────────────
  async function openCreate() {
    createForm.resetFields()
    // dept_admin 固定自己的部门
    if (!isSuperAdmin && currentUser?.dept_id) {
      createForm.setFieldValue('dept_id', currentUser.dept_id)
      createForm.setFieldValue('role', 'employee')
    }
    setCreateOpen(true)
  }

  async function onNameBlur(e: React.FocusEvent<HTMLInputElement>) {
    const name = e.target.value.trim()
    if (!name) return
    try {
      const suggested = await suggestUsername(name)
      createForm.setFieldValue('username', suggested)
      // 如果已选了部门，也自动填员工号
      const deptId = createForm.getFieldValue('dept_id')
      if (deptId) {
        const empNo = await suggestEmployeeNo(deptId)
        createForm.setFieldValue('employee_no', empNo)
      }
    } catch { /* ignore */ }
  }

  async function onDeptChange(deptId: number) {
    try {
      const empNo = await suggestEmployeeNo(deptId)
      createForm.setFieldValue('employee_no', empNo)
    } catch { /* ignore */ }
  }

  async function handleCreate() {
    const vals = await createForm.validateFields()
    try {
      const result: UserCreateResult = await createUser({
        username: vals.username,
        employee_no: vals.employee_no,
        real_name: vals.real_name,
        role: vals.role,
        dept_id: vals.dept_id ?? null,
        email: vals.email || undefined,
        notes: vals.notes || undefined,
      })
      setCreateOpen(false)
      setPwdResult({ username: result.username, password: result.init_password })
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message ?? '创建失败')
    }
  }

  // ── 重置密码 ─────────────────────────────────────────────────
  async function handleResetPwd(u: AdminUser) {
    try {
      const newPwd = await resetPassword(u.id)
      setPwdResult({ username: u.username, password: newPwd })
    } catch { antMsg.error('重置密码失败') }
  }

  // ── 启用 / 禁用 ──────────────────────────────────────────────
  async function handleToggleActive(u: AdminUser) {
    try {
      await setUserStatus(u.id, !u.is_active)
      antMsg.success(u.is_active ? '账号已禁用' : '账号已启用')
      load()
    } catch { antMsg.error('操作失败') }
  }

  // ── 解锁 ──────────────────────────────────────────────────────
  async function handleUnlock(u: AdminUser) {
    try {
      await unlockUser(u.id)
      antMsg.success('账号已解锁')
      load()
    } catch { antMsg.error('解锁失败') }
  }

  const roleLabel: Record<string, { label: string; color: string }> = {
    super_admin: { label: '超级管理员', color: 'gold' },
    dept_admin:  { label: '部门管理员', color: 'blue' },
    employee:    { label: '普通员工',   color: 'default' },
  }

  const cols = [
    { title: '用户名', dataIndex: 'username', key: 'username', width: 130 },
    { title: '姓名', dataIndex: 'real_name', key: 'real_name', width: 100 },
    { title: '员工编号', dataIndex: 'employee_no', key: 'employee_no', width: 100 },
    { title: '角色', dataIndex: 'role', key: 'role', width: 110,
      render: (v: string) => <Tag color={roleLabel[v]?.color}>{roleLabel[v]?.label ?? v}</Tag> },
    { title: '部门', dataIndex: 'dept_name', key: 'dept_name', width: 120,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text> },
    {
      title: '状态', key: 'status', width: 90,
      render: (_: unknown, u: AdminUser) => {
        if (u.locked_at) return <Tag color="red" icon={<LockOutlined />}>已锁定</Tag>
        if (!u.is_active) return <Tag color="default">已禁用</Tag>
        return <Tag color="green">正常</Tag>
      },
    },
    { title: '最后登录', dataIndex: 'last_login_at', key: 'last_login_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: unknown, u: AdminUser) => (
        <Space size={4}>
          <Tooltip title="重置密码">
            <Button size="small" icon={<ReloadOutlined />} onClick={() => handleResetPwd(u)} />
          </Tooltip>
          {u.locked_at && (
            <Tooltip title="解锁账号">
              <Button size="small" icon={<UnlockOutlined />} onClick={() => handleUnlock(u)} />
            </Tooltip>
          )}
          <Tooltip title={u.is_active ? '禁用账号' : '启用账号'}>
            <Button
              size="small"
              danger={u.is_active}
              icon={u.is_active ? <StopOutlined /> : <CheckCircleOutlined />}
              onClick={() => handleToggleActive(u)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12 }}>
        <Title level={5} style={{ margin: 0 }}>账号管理</Title>
        <Space>
          <Input.Search
            placeholder="搜索姓名 / 用户名 / 员工编号"
            allowClear
            style={{ width: 240 }}
            onSearch={(v) => { setKeyword(v); setPage(1); load(1, v) }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建用户</Button>
        </Space>
      </div>

      <Table
        dataSource={users} columns={cols} rowKey="id" loading={loading} size="middle"
        pagination={{ current: page, pageSize: 20, total, onChange: (p) => { setPage(p); load(p) }, showTotal: (t) => `共 ${t} 人` }}
      />

      {/* 新建用户 Modal */}
      <Modal
        title="新建用户" open={createOpen}
        onOk={handleCreate} onCancel={() => setCreateOpen(false)}
        okText="创建" width={500}
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="real_name" label="真实姓名"
            rules={[{ required: true, message: '请输入真实姓名' }]}
          >
            <Input placeholder="如：张三" onBlur={onNameBlur} />
          </Form.Item>
          <Form.Item name="username" label="用户名（登录凭证，创建后不可修改）"
            rules={[
              { required: true, message: '请输入用户名' },
              { pattern: /^[a-z][a-z0-9]*$/, message: '小写字母开头，只含小写字母和数字' },
            ]}
          >
            <Input placeholder="根据姓名自动生成，可手动修改" />
          </Form.Item>
          {isSuperAdmin && (
            <Form.Item name="role" label="角色"
              rules={[{ required: true, message: '请选择角色' }]}
            >
              <Select placeholder="选择角色">
                <Select.Option value="dept_admin">部门管理员</Select.Option>
                <Select.Option value="employee">普通员工</Select.Option>
              </Select>
            </Form.Item>
          )}
          {isSuperAdmin ? (
            <Form.Item name="dept_id" label="所属部门"
              rules={[{ required: true, message: '请选择部门' }]}
            >
              <Select placeholder="选择部门" onChange={onDeptChange}>
                {depts.map(d => (
                  <Select.Option key={d.id} value={d.id}>{d.dept_name}（{d.dept_code}）</Select.Option>
                ))}
              </Select>
            </Form.Item>
          ) : (
            <Form.Item name="role" hidden initialValue="employee">
              <Input />
            </Form.Item>
          )}
          <Form.Item name="employee_no" label="员工编号"
            rules={[{ required: true, message: '请输入员工编号' }]}
          >
            <Input placeholder="根据部门自动生成，可手动修改" />
          </Form.Item>
          <Form.Item name="email" label="邮箱（选填）">
            <Input placeholder="example@company.com" />
          </Form.Item>
          <Form.Item name="notes" label="备注（选填）">
            <Input.TextArea rows={2} placeholder="如：技术部前端负责人" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 密码展示 Modal（一次性） */}
      <Modal
        title="初始密码"
        open={!!pwdResult}
        onOk={() => setPwdResult(null)}
        onCancel={() => setPwdResult(null)}
        cancelText={null}
        footer={<Button type="primary" onClick={() => setPwdResult(null)}>我已记录，关闭</Button>}
      >
        <Alert
          type="warning"
          showIcon
          message="密码仅展示一次，关闭后无法再查看！"
          style={{ marginBottom: 16 }}
        />
        {pwdResult && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="用户名">{pwdResult.username}</Descriptions.Item>
            <Descriptions.Item label="初始密码">
              <Space>
                <Text code style={{ fontSize: 16 }}>{pwdResult.password}</Text>
                <Tooltip title="复制">
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => {
                      navigator.clipboard.writeText(pwdResult.password)
                      antMsg.success('已复制到剪贴板')
                    }}
                  />
                </Tooltip>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
