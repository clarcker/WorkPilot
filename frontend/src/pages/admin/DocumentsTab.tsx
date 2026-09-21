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
  updateDoc, getDocVersionChain,
  type Dept, type AdminUser, type AdminDoc, type VersionChainItem,
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
const LIFECYCLE_LABELS: Record<string, { label: string; color: string }> = {
  effective:  { label: '现行',   color: 'green' },
  superseded: { label: '已替代', color: 'orange' },
  draft:      { label: '草案',   color: 'purple' },
}

export default function DocumentsTab() {
  const currentUser = getStoredUser()
  const isSuperAdmin = currentUser?.role === 'super_admin'

  const [docs, setDocs]         = useState<AdminDoc[]>([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(1)
  const [lifecycleFilter, setLifecycleFilter] = useState<string | undefined>(undefined)
  const [loading, setLoading]   = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [depts, setDepts]       = useState<Dept[]>([])
  const [deptUsers, setDeptUsers] = useState<AdminUser[]>([])
  const [visibility, setVisibility] = useState<string>('dept_only')
  const [uploadForm] = Form.useForm()
  const [fileList, setFileList] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [chainDoc, setChainDoc] = useState<AdminDoc | null>(null)
  const [chainItems, setChainItems] = useState<VersionChainItem[]>([])
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async (p = page, life = lifecycleFilter) => {
    setLoading(true)
    try {
      const res = await listDocs({ page: p, page_size: 20, lifecycle: life || undefined })
      setDocs(res.items)
      setTotal(res.total)
    } catch { antMsg.error('加载文档列表失败') }
    finally { setLoading(false) }
  }, [page, lifecycleFilter])

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
    fd.append('lifecycle', vals.lifecycle || 'effective')
    if (vals.effective_date) fd.append('effective_date', vals.effective_date)
    if (vals.supersedes_doc_id) fd.append('supersedes_doc_id', String(vals.supersedes_doc_id))

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

  async function handleChangeLifecycle(doc: AdminDoc, next: string) {
    try {
      await updateDoc(doc.id, { lifecycle: next })
      antMsg.success(`已切换为 ${LIFECYCLE_LABELS[next]?.label || next}`)
      load()
    } catch { antMsg.error('生命周期更新失败') }
  }

  async function handleShowChain(doc: AdminDoc) {
    try {
      const items = await getDocVersionChain(doc.id)
      setChainItems(items)
      setChainDoc(doc)
    } catch { antMsg.error('加载版本链失败') }
  }

  const cols = [
    { title: '文件名', dataIndex: 'file_name', key: 'file_name', ellipsis: true,
      render: (v: string, d: AdminDoc) => (
        <Space direction="vertical" size={0}>
          <Text ellipsis style={{ maxWidth: 200 }}>{v}</Text>
          {d.category && <Text type="secondary" style={{ fontSize: 11 }}>{d.category}</Text>}
        </Space>
      ) },
    { title: '类型', dataIndex: 'file_type', key: 'file_type', width: 70,
      render: (v: string) => <Tag>{v.toUpperCase()}</Tag> },
    { title: '所属部门', dataIndex: 'dept_name', key: 'dept_name', width: 110,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text> },
    { title: '可见范围', dataIndex: 'visibility', key: 'visibility', width: 100,
      render: (v: string) => {
        const info = VISIBILITY_LABELS[v] ?? { label: v, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      } },
    { title: '生命周期', dataIndex: 'lifecycle', key: 'lifecycle', width: 90,
      render: (v: string, d: AdminDoc) => {
        const info = LIFECYCLE_LABELS[v] ?? { label: v || '现行', color: 'green' }
        return (
          <Space direction="vertical" size={0}>
            <Tag color={info.color}>{info.label}</Tag>
            {d.effective_date && (
              <Text type="secondary" style={{ fontSize: 11 }}>{d.effective_date}</Text>
            )}
          </Space>
        )
      } },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string, d: AdminDoc) => {
        const info = STATUS_LABELS[v] ?? { label: v, color: 'default' }
        return (
          <Tooltip title={d.error_message || ''}>
            <Badge status={info.color as 'default' | 'processing' | 'success' | 'error'} text={info.label} />
          </Tooltip>
        )
      } },
    { title: 'Chunks', dataIndex: 'chunk_count', key: 'chunk_count', width: 70,
      render: (v: number | null) => v ?? '—' },
    { title: '上传者', dataIndex: 'uploaded_by_name', key: 'uploaded_by_name', width: 90,
      render: (v: string | null) => v ?? '—' },
    { title: '上传时间', dataIndex: 'created_at', key: 'created_at', width: 140,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    {
      title: '操作', key: 'action', width: 180,
      render: (_: unknown, doc: AdminDoc) => (
        <Space size={4} wrap>
          <Select
            size="small"
            style={{ width: 88 }}
            value={doc.lifecycle || 'effective'}
            onChange={(v) => handleChangeLifecycle(doc, v)}
            options={Object.entries(LIFECYCLE_LABELS).map(([k, v]) => ({ value: k, label: v.label }))}
          />
          <Button size="small" onClick={() => handleShowChain(doc)}>版本链</Button>
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
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <Space>
          <Title level={5} style={{ margin: 0 }}>文档管理</Title>
          <Select
            allowClear
            placeholder="生命周期"
            style={{ width: 120 }}
            value={lifecycleFilter}
            onChange={(v) => { setLifecycleFilter(v); setPage(1); load(1, v) }}
            options={[
              { value: 'effective', label: '现行' },
              { value: 'superseded', label: '已替代' },
              { value: 'draft', label: '草案' },
            ]}
          />
        </Space>
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

          <Form.Item name="lifecycle" label="生命周期" initialValue="effective">
            <Select
              options={[
                { value: 'effective', label: '现行' },
                { value: 'draft', label: '草案（仅管理员可见）' },
              ]}
            />
          </Form.Item>
          <Form.Item name="effective_date" label="生效日期（选填）">
            <Input placeholder="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="supersedes_doc_id" label="作为新版本替代（选填）">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="选择被替代的旧文档"
              options={docs
                .filter(d => (d.lifecycle || 'effective') !== 'superseded')
                .map(d => ({ value: d.id, label: `${d.file_name}${d.effective_date ? ` (${d.effective_date})` : ''}` }))}
            />
          </Form.Item>
          <Form.Item name="category" label="分类（选填）">
            <Input placeholder="如：行政制度 / 财务规范 / HR 政策" />
          </Form.Item>
          <Form.Item name="version" label="版本号（选填）">
            <Input placeholder="如：v2.1" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`版本链：${chainDoc?.file_name || ''}`}
        open={!!chainDoc}
        onCancel={() => { setChainDoc(null); setChainItems([]) }}
        footer={null}
        width={520}
      >
        {chainItems.map((item) => (
          <div key={item.id} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
            <Space>
              {item.is_self && <Tag color="blue">当前</Tag>}
              <Text strong={item.is_self}>{item.file_name}</Text>
              <Tag color={LIFECYCLE_LABELS[item.lifecycle]?.color || 'default'}>
                {LIFECYCLE_LABELS[item.lifecycle]?.label || item.lifecycle}
              </Tag>
              {item.effective_date && <Text type="secondary">{item.effective_date}</Text>}
              <Text type="secondary">#{item.id}</Text>
            </Space>
          </div>
        ))}
        {chainItems.length <= 1 && (
          <Text type="secondary">该文档暂无上下游版本。</Text>
        )}
      </Modal>
    </div>
  )
}
