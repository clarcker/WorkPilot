/**
 * NotificationBell — 管理端右上角通知（P9 日报等）
 */
import { useEffect, useState } from 'react'
import { Badge, Button, Drawer, Empty, List, Space, Tag, Typography, message as antMsg } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import {
  listNotifications, markAllNotificationsRead, markNotificationRead,
  unreadNotificationCount, type NotificationItem,
} from '../api/admin'

const { Text, Paragraph } = Typography

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)

  async function refresh() {
    try {
      const n = await unreadNotificationCount()
      setUnread(n)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 60_000)
    return () => clearInterval(t)
  }, [])

  async function openDrawer() {
    setOpen(true)
    try {
      const res = await listNotifications({ page: 1, page_size: 30 })
      setItems(res.items)
    } catch {
      antMsg.error('加载通知失败')
    }
  }

  return (
    <>
      <Badge count={unread} size="small">
        <Button type="text" icon={<BellOutlined />} onClick={openDrawer} />
      </Badge>
      <Drawer
        title="通知"
        placement="right"
        width={420}
        open={open}
        onClose={() => setOpen(false)}
        extra={
          <Button size="small" onClick={async () => {
            await markAllNotificationsRead()
            setItems(items.map(i => ({ ...i, is_read: true })))
            setUnread(0)
          }}>全部已读</Button>
        }
      >
        {items.length === 0 ? (
          <Empty description="暂无通知" />
        ) : (
          <List
            dataSource={items}
            renderItem={(n) => (
              <List.Item
                key={n.id}
                onClick={async () => {
                  if (!n.is_read) {
                    await markNotificationRead(n.id)
                    setItems(items.map(x => x.id === n.id ? { ...x, is_read: true } : x))
                    setUnread(Math.max(0, unread - 1))
                  }
                }}
                style={{ opacity: n.is_read ? 0.55 : 1, cursor: 'pointer' }}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color={n.level === 'warning' ? 'orange' : 'blue'}>{n.level}</Tag>
                      <Text strong={!n.is_read}>{n.title}</Text>
                    </Space>
                  }
                  description={
                    <>
                      <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>
                        {n.body}
                      </Paragraph>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {n.created_at ? new Date(n.created_at).toLocaleString('zh-CN') : ''}
                        {n.source ? ` · ${n.source}` : ''}
                      </Text>
                    </>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </>
  )
}
