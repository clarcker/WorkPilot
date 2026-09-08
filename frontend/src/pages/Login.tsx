import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, Alert, Space } from 'antd'
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons'
import { login } from '../api/auth'
import { storeAuth } from '../hooks/useAuth'
import type { StoredAuth } from '../types'

const { Title, Text } = Typography

interface FormValues {
  username: string
  password: string
}

export default function Login() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const redirectMsg = (location.state as { message?: string } | null)?.message ?? null

  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  async function handleSubmit(values: FormValues) {
    setError(null)
    setLoading(true)
    try {
      const data: StoredAuth = await login(values.username, values.password)
      storeAuth(data)
      // Redirect to change-password gate if required, otherwise to chat
      navigate(data.must_change_password ? '/change-password' : '/', { replace: true })
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? '登录失败，请检查用户名和密码'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #e6f4ff 0%, #f0f2f5 60%, #fff1f0 100%)',
      }}
    >
      <Card
        style={{
          width: 400,
          borderRadius: 16,
          boxShadow: '0 8px 32px rgba(0,0,0,0.10)',
          padding: '8px 0',
        }}
      >
        {/* Logo / header */}
        <Space direction="vertical" align="center" style={{ width: '100%', marginBottom: 32 }}>
          <RobotOutlined style={{ fontSize: 48, color: '#1677ff' }} />
          <Title level={3} style={{ margin: 0, color: '#1a1a1a' }}>
            WorkPilot
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            企业智能 Agent 系统
          </Text>
        </Space>

        {redirectMsg && (
          <Alert
            message={redirectMsg}
            type="success"
            showIcon
            style={{ marginBottom: 20, borderRadius: 8 }}
          />
        )}

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            style={{ marginBottom: 20, borderRadius: 8 }}
          />
        )}

        <Form<FormValues>
          layout="vertical"
          onFinish={handleSubmit}
          autoComplete="off"
          requiredMark={false}
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="用户名（拼音全小写）"
              size="large"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="密码"
              size="large"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{ borderRadius: 8 }}
            >
              登 录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
