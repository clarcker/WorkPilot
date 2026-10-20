/**
 * SystemSettingsTab — 系统设置
 */
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Form, Input, Space, Typography, message as antMsg, Spin, Divider,
} from 'antd'
import { getSystemConfig, updateSystemConfig, type SystemConfigMap } from '../../api/admin'

const { Text, Title } = Typography

export default function SystemSettingsTab() {
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
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => form.setFieldValue(item.key, parseInt(e.target.value) || '')}
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
