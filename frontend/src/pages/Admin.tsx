/**
 * 管理后台 — 部门 / 账号 / 文档三合一页面
 * 访问权限：dept_admin 或 super_admin
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Layout, Menu, Button, Table, Tag, Space, Modal, Form, Input,
  Select, Tooltip, Typography, message as antMsg, Upload, Popconfirm,
  Badge, Descriptions, Divider, Alert, Spin, DatePicker,
} from 'antd'
import {
  ArrowLeftOutlined, BankOutlined, TeamOutlined, FileTextOutlined,
  PlusOutlined, ReloadOutlined, InboxOutlined, CopyOutlined,
  LockOutlined, UnlockOutlined, StopOutlined, CheckCircleOutlined,
  DeleteOutlined, SyncOutlined, AuditOutlined, SettingOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { getStoredUser } from '../hooks/useAuth'
import {
  listDepts, createDept, updateDept, deleteDept,
  listUsers, suggestUsername, suggestEmployeeNo, createUser, resetPassword, setUserStatus, unlockUser,
  listDocs, uploadDoc, reindexDoc, archiveDoc, setDocPermissions,
  listAuditLogs, getSystemConfig, updateSystemConfig, getSystemLogs,
  type Dept, type AdminUser, type UserCreateResult, type AdminDoc,
  type AuditLogItem, type SystemConfigMap, type LogEntry,
} from '../api/admin'

const { Sider, Content } = Layout
const { Text, Title } = Typography
const { Dragger } = Upload

// ═══════════════════════════════════════════════════════════════════
//  Departments Tab
// ═══════════════════════════════════════════════════════════════════

function DepartmentsTab() {
  const [depts, setDepts]       = useState<Dept[]>([])
  const [loading, setLoading]   = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Dept | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try { setDepts(await listDepts()) }
    catch { antMsg.error('加载部门列表失败') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  function openCreate() { setEditTarget(null); form.resetFields(); setModalOpen(true) }
  function openEdit(d: Dept) {
    setEditTarget(d)
    form.setFieldsValue({ dept_code: d.dept_code, dept_name: d.dept_name })
    setModalOpen(true)
  }

  async function handleOk() {
    const vals = await form.validateFields()
    try {
      if (editTarget) {
        await updateDept(editTarget.id, vals.dept_name)
        antMsg.success('部门名称已更新')
      } else {
        await createDept(vals)
        antMsg.success('部门创建成功')
      }
      setModalOpen(false)
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail?.message ?? '操作失败'
      antMsg.error(msg)
    }
  }

  async function handleDelete(d: Dept) {
    try {
      await deleteDept(d.id)
      antMsg.success('部门已删除')
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail?.message ?? '删除失败'
      antMsg.error(msg)
    }
  }

  const cols = [
    { title: '部门代码', dataIndex: 'dept_code', key: 'dept_code', width: 120,
      render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '部门名称', dataIndex: 'dept_name', key: 'dept_name' },
    { title: '人数', dataIndex: 'user_count', key: 'user_count', width: 80,
      render: (v: number) => <Badge count={v} color="#1677ff" showZero /> },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, d: Dept) => (
        <Space>
          <Button size="small" onClick={() => openEdit(d)}>改名</Button>
          <Popconfirm
            title={d.user_count > 0 ? `该部门还有 ${d.user_count} 名用户，无法删除` : '确认删除此部门？'}
            onConfirm={() => d.user_count === 0 && handleDelete(d)}
            okText="确认删除" cancelText="取消"
            okButtonProps={{ danger: true, disabled: d.user_count > 0 }}
          >
            <Button size="small" danger disabled={d.user_count > 0} icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>部门管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建部门</Button>
      </div>
      <Table dataSource={depts} columns={cols} rowKey="id" loading={loading} size="middle" />

      <Modal
        title={editTarget ? '修改部门名称' : '新建部门'}
        open={modalOpen}
        onOk={handleOk}
        onCancel={() => setModalOpen(false)}
        okText="保存"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {!editTarget && (
            <Form.Item name="dept_code" label="部门代码"
              rules={[
                { required: true, message: '请输入部门代码' },
                { pattern: /^[A-Z0-9]+$/, message: '大写字母或数字，如 HR、RD01' },
              ]}
            >
              <Input placeholder="大写字母，如 HR / RD / SALES" maxLength={20} style={{ textTransform: 'uppercase' }} />
            </Form.Item>
          )}
          <Form.Item name="dept_name" label="部门名称"
            rules={[{ required: true, message: '请输入部门名称' }]}
          >
            <Input placeholder="如：人力资源部、研发部" maxLength={50} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
//  Users Tab
// ═══════════════════════════════════════════════════════════════════

function UsersTab() {
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

// ═══════════════════════════════════════════════════════════════════
//  Documents Tab
// ═══════════════════════════════════════════════════════════════════

const VISIBILITY_LABELS: Record<string, { label: string; color: string }> = {
  global:         { label: '全体共享',   color: 'green' },
  non_customer:   { label: '非客服共享', color: 'cyan' },
  dept_only:      { label: '本部门',     color: 'blue' },
  specific_users: { label: '指定人员',   color: 'purple' },
}
const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  processing: { label: '处理中', color: 'processing' },
  ready:      { label: '已就绪', color: 'success' },
  failed:     { label: '处理失败', color: 'error' },
  archived:   { label: '已归档', color: 'default' },
}

function DocumentsTab() {
  const currentUser = getStoredUser()
  const isSuperAdmin = currentUser?.role === 'super_admin'

  const [docs, setDocs]         = useState<AdminDoc[]>([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(1)
  const [loading, setLoading]   = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [depts, setDepts]       = useState<Dept[]>([])
  const [deptUsers, setDeptUsers] = useState<AdminUser[]>([])
  const [visibility, setVisibility] = useState<string>('dept_only')
  const [uploadForm] = Form.useForm()
  const [fileList, setFileList] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async (p = page) => {
    setLoading(true)
    try {
      const res = await listDocs({ page: p, page_size: 20 })
      setDocs(res.items)
      setTotal(res.total)
    } catch { antMsg.error('加载文档列表失败') }
    finally { setLoading(false) }
  }, [page])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (isSuperAdmin) listDepts().then(setDepts).catch(() => {}) }, [isSuperAdmin])

  // 有处理中的文档时自动轮询刷新
  useEffect(() => {
    const hasPending = docs.some(d => d.status === 'processing')
    if (hasPending && !pollingRef.current) {
      pollingRef.current = setInterval(() => load(), 4000)
    } else if (!hasPending && pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
    }
  }, [docs, load])

  async function loadDeptUsers(deptId: number) {
    try {
      const res = await listUsers({ dept_id: deptId, page_size: 200 })
      setDeptUsers(res.items.filter(u => u.role === 'employee'))
    } catch { setDeptUsers([]) }
  }

  function onUploadDeptChange(deptId: number) {
    uploadForm.setFieldValue('specific_user_ids', [])
    loadDeptUsers(deptId)
  }

  function onVisibilityChange(v: string) {
    setVisibility(v)
    if (v === 'specific_users') {
      const deptId = uploadForm.getFieldValue('dept_id') ?? currentUser?.dept_id
      if (deptId) loadDeptUsers(deptId)
    }
  }

  async function handleUpload() {
    const vals = await uploadForm.validateFields()
    if (fileList.length === 0) { antMsg.warning('请选择文件'); return }

    const fd = new FormData()
    fd.append('file', fileList[0])
    const deptId = vals.dept_id ?? currentUser?.dept_id
    if (deptId) fd.append('dept_id', String(deptId))
    fd.append('visibility', vals.visibility || 'dept_only')
    if (vals.category) fd.append('category', vals.category)
    if (vals.version)  fd.append('version',  vals.version)

    setUploading(true)
    try {
      const doc = await uploadDoc(fd)
      if (vals.visibility === 'specific_users' && vals.specific_user_ids?.length) {
        await setDocPermissions(doc.id, vals.specific_user_ids)
      }
      antMsg.success('上传成功，后台处理中…')
      setUploadOpen(false)
      setFileList([])
      setVisibility('dept_only')
      uploadForm.resetFields()
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message ?? '上传失败')
    } finally { setUploading(false) }
  }

  async function handleReindex(doc: AdminDoc) {
    try { await reindexDoc(doc.id); antMsg.success('已重新触发索引'); load() }
    catch { antMsg.error('操作失败') }
  }

  async function handleArchive(doc: AdminDoc) {
    try { await archiveDoc(doc.id); antMsg.success('文档已归档'); load() }
    catch { antMsg.error('操作失败') }
  }

  const cols = [
    { title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true,
      render: (v: string, d: AdminDoc) => (
        <Space direction="vertical" size={0}>
          <Text ellipsis style={{ maxWidth: 220 }}>{v}</Text>
          {d.category && <Text type="secondary" style={{ fontSize: 11 }}>{d.category}</Text>}
        </Space>
      ) },
    { title: '类型', dataIndex: 'file_type', key: 'file_type', width: 70,
      render: (v: string) => <Tag>{v.toUpperCase()}</Tag> },
    { title: '所属部门', dataIndex: 'dept_name', key: 'dept_name', width: 120,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text> },
    { title: '可见范围', dataIndex: 'visibility', key: 'visibility', width: 110,
      render: (v: string) => {
        const info = VISIBILITY_LABELS[v] ?? { label: v, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      } },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string, d: AdminDoc) => {
        const info = STATUS_LABELS[v] ?? { label: v, color: 'default' }
        return (
          <Tooltip title={d.error_message || ''}>
            <Badge status={info.color as 'default' | 'processing' | 'success' | 'error'} text={info.label} />
          </Tooltip>
        )
      } },
    { title: 'Chunks', dataIndex: 'chunk_count', key: 'chunk_count', width: 80,
      render: (v: number | null) => v ?? '—' },
    { title: '上传者', dataIndex: 'uploaded_by_name', key: 'uploaded_by_name', width: 100,
      render: (v: string | null) => v ?? '—' },
    { title: '上传时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, doc: AdminDoc) => (
        <Space size={4}>
          {doc.status === 'failed' && (
            <Tooltip title="重新索引">
              <Button size="small" icon={<SyncOutlined />} onClick={() => handleReindex(doc)} />
            </Tooltip>
          )}
          <Popconfirm
            title="归档后文档将从检索结果中移除，确认操作？"
            onConfirm={() => handleArchive(doc)}
            okText="确认归档" cancelText="取消" okButtonProps={{ danger: true }}
          >
            <Tooltip title="归档">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0 }}>文档管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setFileList([]); uploadForm.resetFields(); setUploadOpen(true) }}>
          上传文档
        </Button>
      </div>

      <Table
        dataSource={docs} columns={cols} rowKey="id" loading={loading} size="middle"
        pagination={{ current: page, pageSize: 20, total, onChange: (p) => { setPage(p); load(p) }, showTotal: (t) => `共 ${t} 份` }}
      />

      <Modal
        title="上传文档" open={uploadOpen}
        onOk={handleUpload} onCancel={() => setUploadOpen(false)}
        okText="上传" confirmLoading={uploading} width={520}
      >
        <Form form={uploadForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="选择文件（.pdf / .docx / .doc / .txt / .md）" required>
            <Dragger
              multiple={false}
              accept=".pdf,.docx,.doc,.txt,.md"
              beforeUpload={(file) => { setFileList([file]); return false }}
              onRemove={() => setFileList([])}
              fileList={fileList.map(f => ({ uid: f.name, name: f.name, size: f.size, type: f.type }))}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽文件到此处</p>
              <p className="ant-upload-hint">支持 PDF / Word / TXT / Markdown，单文件最大 50 MB</p>
            </Dragger>
          </Form.Item>

          {isSuperAdmin && (
            <Form.Item name="dept_id" label="所属部门"
              rules={[{ required: true, message: '请选择目标部门' }]}
            >
              <Select placeholder="选择部门" onChange={onUploadDeptChange}>
                {depts.map(d => (
                  <Select.Option key={d.id} value={d.id}>{d.dept_name}（{d.dept_code}）</Select.Option>
                ))}
              </Select>
            </Form.Item>
          )}

          <Form.Item name="visibility" label="可见范围" initialValue="dept_only">
            <Select onChange={onVisibilityChange}>
              <Select.Option value="global">全体共享</Select.Option>
              <Select.Option value="non_customer">非客服共享</Select.Option>
              <Select.Option value="dept_only">本部门</Select.Option>
              <Select.Option value="specific_users">指定人员</Select.Option>
            </Select>
          </Form.Item>

          {visibility === 'specific_users' && (
            <Form.Item name="specific_user_ids" label="指定可访问成员"
              rules={[{ required: true, message: '请至少选择一名成员' }]}
            >
              <Select mode="multiple" placeholder="选择本部门员工" allowClear>
                {deptUsers.map(u => (
                  <Select.Option key={u.id} value={u.id}>
                    {u.real_name}（{u.username}）
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          )}

          <Form.Item name="category" label="分类（选填）">
            <Input placeholder="如：行政制度 / 财务规范 / HR 政策" />
          </Form.Item>
          <Form.Item name="version" label="版本号（选填）">
            <Input placeholder="如：v2.1" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
//  Audit Logs Tab（仅超级管理员）
// ═══════════════════════════════════════════════════════════════════

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

function AuditLogsTab() {
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

// ═══════════════════════════════════════════════════════════════════
//  System Settings Tab（仅超级管理员）
// ═══════════════════════════════════════════════════════════════════

function SystemSettingsTab() {
  const [config, setConfig]   = useState<SystemConfigMap>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState<string | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getSystemConfig()
      setConfig(data)
      const initialValues: Record<string, number> = {}
      Object.entries(data).forEach(([k, v]) => { initialValues[k] = v.value })
      form.setFieldsValue(initialValues)
    } catch { antMsg.error('加载系统配置失败') }
    finally { setLoading(false) }
  }, [form])

  useEffect(() => { load() }, [load])

  async function handleSave(key: string) {
    const value = form.getFieldValue(key)
    if (!Number.isInteger(value) || value <= 0) {
      antMsg.warning('请输入正整数')
      return
    }
    setSaving(key)
    try {
      await updateSystemConfig(key, value)
      antMsg.success('配置已更新')
      load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      antMsg.error(typeof msg === 'string' ? msg : (msg as { message?: string })?.message ?? '保存失败')
    } finally { setSaving(null) }
  }

  const items = Object.entries(config).map(([key, meta]) => ({ key, ...meta }))

  return (
    <div style={{ maxWidth: 600 }}>
      <Title level={5} style={{ marginBottom: 20 }}>系统设置 — 对话记录上限</Title>
      {loading ? <Spin /> : (
        <Form form={form} layout="vertical">
          {items.map(item => (
            <Form.Item
              key={item.key}
              name={item.key}
              label={
                <Space>
                  <span>{item.label}</span>
                  <Text type="secondary" style={{ fontSize: 12 }}>（默认：{item.default}）</Text>
                </Space>
              }
            >
              <Space>
                <Form.Item name={item.key} noStyle>
                  <Input
                    type="number"
                    min={1}
                    style={{ width: 140 }}
                    onChange={e => form.setFieldValue(item.key, parseInt(e.target.value) || '')}
                  />
                </Form.Item>
                <Button
                  type="primary"
                  size="small"
                  loading={saving === item.key}
                  onClick={() => handleSave(item.key)}
                >
                  保存
                </Button>
              </Space>
            </Form.Item>
          ))}
        </Form>
      )}
      <Divider />
      <Text type="secondary" style={{ fontSize: 12 }}>
        · 每用户最大会话数：超出后最旧会话自动转为归档状态<br />
        · 每会话最大消息数：超出后截断最早消息<br />
        · 归档数据保留天数：到期后物理删除，不可恢复
      </Text>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
//  System Logs Tab（仅超级管理员）
// ═══════════════════════════════════════════════════════════════════

const LOG_LEVEL_COLORS: Record<string, string> = {
  DEBUG:     'default',
  INFO:      'blue',
  WARNING:   'orange',
  ERROR:     'red',
  CRITICAL:  'magenta',
}

function SystemLogsTab() {
  const [logs, setLogs]             = useState<LogEntry[]>([])
  const [total, setTotal]           = useState(0)
  const [page, setPage]             = useState(1)
  const [loading, setLoading]       = useState(false)
  const [logDate, setLogDate]       = useState<string>(dayjs().format('YYYY-MM-DD'))
  const [filterLevel, setFilterLevel] = useState<string>('')
  const [keyword, setKeyword]       = useState<string>('')
  const [fileExists, setFileExists] = useState(true)

  const load = useCallback(async (p = page, date = logDate, level = filterLevel, kw = keyword) => {
    setLoading(true)
    try {
      const res = await getSystemLogs({
        log_date: date,
        level: level || undefined,
        keyword: kw || undefined,
        page: p,
        page_size: 100,
      })
      setLogs(res.items)
      setTotal(res.total)
      setFileExists(res.file_exists)
    } catch {
      antMsg.error('加载日志失败')
    } finally {
      setLoading(false)
    }
  }, [page, logDate, filterLevel, keyword])

  useEffect(() => { load() }, [load])

  function handleDateChange(date: dayjs.Dayjs | null) {
    const d = date ? date.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD')
    setLogDate(d)
    setPage(1)
    load(1, d, filterLevel, keyword)
  }

  function handleLevelChange(level: string) {
    setFilterLevel(level)
    setPage(1)
    load(1, logDate, level, keyword)
  }

  function handleSearch(kw: string) {
    setKeyword(kw)
    setPage(1)
    load(1, logDate, filterLevel, kw)
  }

  const cols = [
    { title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 190,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
    { title: '级别', dataIndex: 'level', key: 'level', width: 90,
      render: (v: string) => <Tag color={LOG_LEVEL_COLORS[v] ?? 'default'}>{v}</Tag> },
    { title: '位置', dataIndex: 'location', key: 'location', width: 200,
      render: (v: string) => <Text type="secondary" ellipsis style={{ fontSize: 12, maxWidth: 180 }}>{v}</Text> },
    { title: '请求ID', dataIndex: 'request_id', key: 'request_id', width: 100,
      render: (v: string) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : '—' },
    { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <Title level={5} style={{ margin: 0 }}>系统日志</Title>
        <Space wrap>
          <DatePicker
            defaultValue={dayjs()}
            onChange={handleDateChange}
            allowClear={false}
            style={{ width: 150 }}
          />
          <Select
            value={filterLevel || undefined}
            onChange={handleLevelChange}
            placeholder="日志级别"
            allowClear
            style={{ width: 120 }}
          >
            <Select.Option value="DEBUG">DEBUG</Select.Option>
            <Select.Option value="INFO">INFO</Select.Option>
            <Select.Option value="WARNING">WARNING</Select.Option>
            <Select.Option value="ERROR">ERROR</Select.Option>
            <Select.Option value="CRITICAL">CRITICAL</Select.Option>
          </Select>
          <Input.Search
            placeholder="关键词搜索"
            allowClear
            style={{ width: 200 }}
            onSearch={handleSearch}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
        </Space>
      </div>

      {!fileExists ? (
        <Alert
          type="info"
          showIcon
          message={`${logDate} 的日志文件不存在`}
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Table
          dataSource={logs} columns={cols} rowKey={(_, i) => String(i)} loading={loading} size="small"
          pagination={{
            current: page, pageSize: 100, total,
            onChange: (p) => { setPage(p); load(p) },
            showTotal: (t) => `共 ${t} 条`,
            showSizeChanger: false,
          }}
          scroll={{ x: 900 }}
        />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
//  Admin Page Shell
// ═══════════════════════════════════════════════════════════════════

type TabKey = 'departments' | 'users' | 'documents' | 'audit' | 'settings' | 'logs'

export default function Admin() {
  const navigate = useNavigate()
  const currentUser = getStoredUser()
  const isSuperAdmin = currentUser?.role === 'super_admin'
  const [activeTab, setActiveTab] = useState<TabKey>(isSuperAdmin ? 'departments' : 'users')

  const menuItems = [
    ...(isSuperAdmin ? [{ key: 'departments', icon: <BankOutlined />,    label: '部门管理' }] : []),
    { key: 'users',     icon: <TeamOutlined />,     label: '账号管理' },
    { key: 'documents', icon: <FileTextOutlined />,  label: '文档管理' },
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
    audit:       <AuditLogsTab />,
    logs:        <SystemLogsTab />,
    settings:    <SystemSettingsTab />,
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider width={200} theme="light" style={{ borderRight: '1px solid #f0f0f0', flexShrink: 0 }}>
        {/* 顶部返回 + 标题 */}
        <div style={{ padding: '14px 16px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button size="small" type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/')} />
          <span style={{ fontWeight: 700, fontSize: 15 }}>管理后台</span>
        </div>
        {/* 底部用户信息 */}
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
