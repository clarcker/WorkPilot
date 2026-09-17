/**
 * DocumentsTab — 文档管理
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Button, Table, Tag, Space, Modal, Form, Input,
  Select, Typography, message as antMsg, Upload,
  Popconfirm, Badge, Tooltip,
} from 'antd'
import {
  PlusOutlined, InboxOutlined, DeleteOutlined, SyncOutlined,
} from '@ant-design/icons'
import { getStoredUser } from '../../hooks/useAuth'
import {
  listDepts, listUsers, listDocs, uploadDoc, reindexDoc, archiveDoc, setDocPermissions,
  type Dept, type AdminUser, type AdminDoc,
} from '../../api/admin'

const { Text, Title } = Typography
const { Dragger } = Upload

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

export default function DocumentsTab() {
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
