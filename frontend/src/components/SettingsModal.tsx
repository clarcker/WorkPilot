/**
 * SettingsModal — personal settings drawer (nickname + password change).
 * Triggered from the Chat sidebar user area.
 */
import { useState } from 'react'
import {
  Modal,
  Tabs,
  Form,
  Input,
  Button,
  Alert,
  Space,
  Typography,
  message as antMessage,
} from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import client from '../api/client'
import { getStoredUser, storeAuth } from '../hooks/useAuth'

const { Text } = Typography

interface Props {
  open: boolean
  onClose: () => void
}

// ── Nickname tab ──────────────────────────────────────────────────

function NicknameForm({ onSuccess }: { onSuccess: (name: string) => void }) {
  const user = getStoredUser()
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const [form] = Form.useForm<{ display_name: string }>()

  async function handleSubmit(values: { display_name: string }) {
    setError(null)
    setLoading(true)
    try {
      await client.patch('/auth/me', { display_name: values.display_name })
      // Update local cached user info
      const stored = getStoredUser()
      if (stored) {
        storeAuth({ ...stored, display_name: values.display_name })
      }
      antMessage.success('昵称修改成功')
      onSuccess(values.display_name)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? '修改失败，请重试'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleSubmit}
      requiredMark={false}
      initialValues={{ display_name: user?.display_name ?? '' }}
      style={{ paddingTop: 8 }}
    >
      <Form.Item label="当前用户名">
        <Text type="secondary">{user?.username}</Text>
      </Form.Item>

      {error && (
        <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />
      )}

      <Form.Item
        name="display_name"
        label="昵称"
        rules={[
          { required: true, message: '请输入昵称' },
          { max: 50, message: '昵称最多 50 个字符' },
        ]}
      >
        <Input
          prefix={<UserOutlined style={{ color: '#bfbfbf' }} />}
          placeholder="输入新昵称"
          size="large"
        />
      </Form.Item>

      <Form.Item style={{ marginBottom: 0 }}>
        <Button type="primary" htmlType="submit" loading={loading} style={{ borderRadius: 8 }}>
          保存昵称
        </Button>
      </Form.Item>
    </Form>
  )
}

// ── Password tab ──────────────────────────────────────────────────

function PasswordForm({ onSuccess }: { onSuccess: () => void }) {
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const [form] = Form.useForm<{
    old_password: string
    new_password: string
    confirm_password: string
  }>()

  async function handleSubmit(values: {
    old_password: string
    new_password: string
    confirm_password: string
  }) {
    setError(null)
    setLoading(true)
    try {
      await client.post('/auth/change-password', {
        old_password: values.old_password,
        new_password: values.new_password,
      })
      antMessage.success('密码修改成功，请重新登录')
      form.resetFields()
      onSuccess()
    } catch (err: unknown) {
      const raw = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof raw === 'string' ? raw : (raw as { message?: string })?.message ?? '修改失败，请重试'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleSubmit}
      requiredMark={false}
      autoComplete="off"
      style={{ paddingTop: 8 }}
    >
      {error && (
        <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />
      )}

      <Form.Item
        name="old_password"
        label="当前密码"
        rules={[{ required: true, message: '请输入当前密码' }]}
      >
        <Input.Password
          prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
          placeholder="输入当前密码"
          size="large"
        />
      </Form.Item>

      <Form.Item
        name="new_password"
        label="新密码"
        rules={[
          { required: true, message: '请输入新密码' },
          { min: 8, message: '密码至少 8 位' },
        ]}
      >
        <Input.Password
          prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
          placeholder="至少 8 位"
          size="large"
        />
      </Form.Item>

      <Form.Item
        name="confirm_password"
        label="确认新密码"
        dependencies={['new_password']}
        rules={[
          { required: true, message: '请确认新密码' },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('new_password') === value) return Promise.resolve()
              return Promise.reject(new Error('两次输入的密码不一致'))
            },
          }),
        ]}
      >
        <Input.Password
          prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
          placeholder="再次输入新密码"
          size="large"
        />
      </Form.Item>

      <Form.Item style={{ marginBottom: 0 }}>
        <Space>
          <Button type="primary" htmlType="submit" loading={loading} style={{ borderRadius: 8 }}>
            修改密码
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            修改后将自动退出，需重新登录
          </Text>
        </Space>
      </Form.Item>
    </Form>
  )
}

// ── Modal wrapper ─────────────────────────────────────────────────

export default function SettingsModal({ open, onClose }: Props) {
  // After password change the session is invalidated — redirect to login
  function handlePasswordSuccess() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
    window.location.href = '/login'
  }

  const items = [
    {
      key: 'nickname',
      label: '修改昵称',
      children: <NicknameForm onSuccess={() => { /* sidebar will re-read from localStorage */ }} />,
    },
    {
      key: 'password',
      label: '修改密码',
      children: <PasswordForm onSuccess={handlePasswordSuccess} />,
    },
  ]

  return (
    <Modal
      title="个人设置"
      open={open}
      onCancel={onClose}
      footer={null}
      width={460}
      destroyOnHidden
    >
      <Tabs items={items} />
    </Modal>
  )
}
