/**
 * ChangePassword — full-page gate shown when must_change_password === true.
 * User cannot navigate away until password is changed.
 * After success the token is revoked server-side; we clear local storage
 * and redirect to /login so the user authenticates with the new password.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, Alert, Space } from 'antd'
import { LockOutlined, RobotOutlined } from '@ant-design/icons'
import client from '../api/client'
import { clearAuth, getStoredUser } from '../hooks/useAuth'

const { Title, Text } = Typography

interface FormValues {
  new_password: string
  confirm_password: string
}

export default function ChangePassword() {
  const navigate  = useNavigate()
  const user      = getStoredUser()
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  async function handleSubmit(values: FormValues) {
    setError(null)
    setLoading(true)
    try {
      await client.post('/auth/change-password', {
        new_password: values.new_password,
        // old_password not required when must_change_password === true
      })
      // Server revokes token — clear local auth and re-login
      clearAuth()
      navigate('/login', {
        replace: true,
        state: { message: '密码已修改，请用新密码登录' },
      })
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
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #fff7e6 0%, #f0f2f5 60%, #e6f4ff 100%)',
      }}
    >
      <Card
        style={{
          width: 420,
          borderRadius: 16,
          boxShadow: '0 8px 32px rgba(0,0,0,0.10)',
        }}
      >
        <Space direction="vertical" align="center" style={{ width: '100%', marginBottom: 28 }}>
          <RobotOutlined style={{ fontSize: 40, color: '#fa8c16' }} />
          <Title level={4} style={{ margin: 0 }}>首次登录，请修改密码</Title>
          <Text type="secondary" style={{ fontSize: 13, textAlign: 'center' }}>
            你好，{user?.display_name ?? user?.username}。<br />
            出于安全原因，请先设置一个新密码才能继续使用系统。
          </Text>
        </Space>

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
          requiredMark={false}
          autoComplete="off"
        >
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
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve()
                  }
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
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{ borderRadius: 8 }}
            >
              修改密码并登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
