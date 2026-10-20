/**
 * DepartmentsTab — 部门管理
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Modal, Form, Input,
  Typography, message as antMsg, Popconfirm, Badge,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import {
  listDepts, createDept, updateDept, deleteDept,
  type Dept,
} from '../../api/admin'

const { Title } = Typography

export default function DepartmentsTab() {
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
