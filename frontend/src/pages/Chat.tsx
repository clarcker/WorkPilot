import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Layout,
  List,
  Button,
  Input,
  Avatar,
  Typography,
  Spin,
  Tooltip,
  Dropdown,
  Modal,
  message as antMessage,
  Empty,
  Badge,
} from 'antd'
import SettingsModal from '../components/SettingsModal'

import {
  PlusOutlined,
  SendOutlined,
  DeleteOutlined,
  SettingOutlined,
  RobotOutlined,
  UserOutlined,
  LogoutOutlined,
  EllipsisOutlined,
  LoadingOutlined,
  DashboardOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { logout } from '../api/auth'
import {
  listConversations,
  getConversation,
  deleteConversation,
  streamChat,
} from '../api/chat'
import { getStoredUser } from '../hooks/useAuth'
import SourceCard from '../components/SourceCard'
import ToolCallCard from '../components/ToolCallCard'
import type { Conversation, Message, Source, ToolCallInfo } from '../types'

const { Sider, Content } = Layout
const { Text } = Typography
const { TextArea } = Input

// ─── types ───────────────────────────────────────────────────────

interface UiMessage {
  id: number | string   // string for optimistic / streaming messages
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  toolCalls?: ToolCallInfo[]
  streaming?: boolean
}

// ─── helpers ─────────────────────────────────────────────────────

function formatTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  if (diffDays === 0) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1) return '昨天'
  if (diffDays < 7)  return `${diffDays}天前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function conversationTitle(conv: Conversation) {
  return conv.title || `对话 #${conv.id}`
}

// ─── component ───────────────────────────────────────────────────

export default function Chat() {
  const navigate = useNavigate()
  const user = getStoredUser()

  const [conversations, setConversations]     = useState<Conversation[]>([])
  const [activeId, setActiveId]               = useState<number | null>(null)
  const [messages, setMessages]               = useState<UiMessage[]>([])
  const [loadingConvs, setLoadingConvs]       = useState(false)
  const [loadingMsgs, setLoadingMsgs]         = useState(false)
  const [streaming, setStreaming]             = useState(false)
  const [inputValue, setInputValue]           = useState('')
  const [siderCollapsed, setSiderCollapsed]   = useState(false)
  const [settingsOpen,   setSettingsOpen]     = useState(false)
  const [showRetry, setShowRetry]             = useState(false)

  const bottomRef   = useRef<HTMLDivElement>(null)
  const abortRef    = useRef<AbortController | null>(null)
  const timeoutRef  = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastQueryRef = useRef<string>('')

  // ── cleanup timeout on unmount ────────────────────────────────
  useEffect(() => {
    return () => {
      clearTimeoutTimer()
    }
  }, [])

  // ── scroll to bottom on new messages ──────────────────────────
  useLayoutEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── load conversation list ─────────────────────────────────────
  const refreshConversations = useCallback(async () => {
    setLoadingConvs(true)
    try {
      const list = await listConversations()
      setConversations(list)
    } catch {
      antMessage.error('加载会话列表失败')
    } finally {
      setLoadingConvs(false)
    }
  }, [])

  useEffect(() => { refreshConversations() }, [refreshConversations])

  // ── select / load a conversation ──────────────────────────────
  async function openConversation(id: number) {
    if (streaming) return          // don't switch mid-stream
    if (id === activeId) return
    
    // Clean up any pending timeout/retry state
    clearTimeoutTimer()
    setShowRetry(false)
    
    setActiveId(id)
    setMessages([])
    setLoadingMsgs(true)
    try {
      const detail = await getConversation(id)
      const uiMsgs: UiMessage[] = detail.messages.map((m: Message) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        sources: m.sources ?? undefined,
      }))
      setMessages(uiMsgs)
    } catch {
      antMessage.error('加载消息失败')
    } finally {
      setLoadingMsgs(false)
    }
  }

  // ── new conversation ───────────────────────────────────────────
  function newConversation() {
    if (streaming) return
    
    // Clean up any pending timeout/retry state
    clearTimeoutTimer()
    setShowRetry(false)
    
    setActiveId(null)
    setMessages([])
  }

  // ── delete conversation ────────────────────────────────────────
  function handleDelete(conv: Conversation) {
    Modal.confirm({
      title: '删除对话',
      content: `确认删除「${conversationTitle(conv)}」？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await deleteConversation(conv.id)
        setConversations((prev) => prev.filter((c) => c.id !== conv.id))
        if (activeId === conv.id) {
          setActiveId(null)
          setMessages([])
        }
      },
    })
  }

  // ── timeout timer management ──────────────────────────────────
  const TIMEOUT_MS = 120_000 // 2 minutes

  function startTimeoutTimer() {
    clearTimeoutTimer()
    timeoutRef.current = setTimeout(() => {
      setShowRetry(true)
    }, TIMEOUT_MS)
  }

  function resetTimeoutTimer() {
    setShowRetry(false)
    startTimeoutTimer()
  }

  function clearTimeoutTimer() {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }

  // ── send message ───────────────────────────────────────────────
  async function sendMessage(query?: string) {
    const q = query ?? inputValue.trim()
    if (!q || streaming) return
    setInputValue('')
    setShowRetry(false)
    lastQueryRef.current = q

    // Optimistic user bubble
    const userMsg: UiMessage = { id: `u-${Date.now()}`, role: 'user', content: q }
    const assistantMsgId = `a-${Date.now()}`
    const assistantMsg: UiMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      streaming: true,
    }
    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    let currentConvId = activeId
    let tokenBuffer   = ''
    let finalSources: Source[] = []

    // Start timeout timer
    startTimeoutTimer()

    try {
      await streamChat(
        q,
        activeId,
        (evt) => {
          // Reset timer on any event (connection is alive)
          resetTimeoutTimer()

          switch (evt.type) {
            case 'conversation_id':
              currentConvId = evt.content
              setActiveId(evt.content)
              break

            case 'token':
              tokenBuffer += evt.content
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: tokenBuffer }
                    : m,
                ),
              )
              break

            case 'sources':
              finalSources = evt.content
              // 立即显示找到的资料
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, sources: finalSources.length ? finalSources : undefined }
                    : m,
                ),
              )
              break

            case 'tool_call':
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last && last.role === 'assistant' && last.streaming) {
                  const updated = { ...last, toolCalls: [...(last.toolCalls || []), evt.content] }
                  return [...prev.slice(0, -1), updated]
                }
                return prev
              })
              break

            case 'done':
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, streaming: false, sources: finalSources.length ? finalSources : undefined }
                    : m,
                ),
              )
              break

            case 'error':
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, streaming: false, content: `❌ ${evt.content}` }
                    : m,
                ),
              )
              break
          }
        },
        ctrl.signal,
      )
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, streaming: false, content: '❌ 请求失败，请重试' }
              : m,
          ),
        )
      }
    } finally {
      clearTimeoutTimer()
      setStreaming(false)
      setShowRetry(false)
      abortRef.current = null
      // Refresh sidebar to show new / updated conversation title
      if (currentConvId !== null) {
        refreshConversations().then(() => {
          setActiveId(currentConvId)
        })
      }
    }
  }

  // ── retry last query ──────────────────────────────────────────
  function handleRetry() {
    // Cancel current request
    if (abortRef.current) {
      abortRef.current.abort()
    }
    // Remove the last assistant message (the one that timed out)
    setMessages((prev) => prev.filter((m) => m.role !== 'assistant' || m.content !== ''))
    // Resend
    setTimeout(() => {
      sendMessage(lastQueryRef.current)
    }, 100)
  }

  // ── keyboard shortcut (Enter to send, Shift+Enter newline) ────
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // ── logout ────────────────────────────────────────────────────
  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  // ─── render ──────────────────────────────────────────────────

  return (
    <Layout style={{ height: '100vh', background: '#fff' }}>
      {/* ── Sidebar ───────────────────────────────────────────── */}
      <Sider
        width={260}
        collapsible
        collapsed={siderCollapsed}
        onCollapse={setSiderCollapsed}
        theme="light"
        style={{
          borderRight: '1px solid #f0f0f0',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: siderCollapsed ? '16px 8px' : '16px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            justifyContent: siderCollapsed ? 'center' : 'flex-start',
          }}
        >
          <RobotOutlined style={{ fontSize: 22, color: '#1677ff', flexShrink: 0 }} />
          {!siderCollapsed && (
            <span style={{ fontWeight: 700, fontSize: 16, color: '#1a1a1a', whiteSpace: 'nowrap' }}>
              WorkPilot
            </span>
          )}
        </div>

        {/* New Chat button */}
        <div style={{ padding: siderCollapsed ? '12px 8px' : '12px 16px' }}>
          <Tooltip title={siderCollapsed ? '新对话' : ''} placement="right">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              block={!siderCollapsed}
              onClick={newConversation}
              style={{ borderRadius: 8 }}
            >
              {!siderCollapsed && '新对话'}
            </Button>
          </Tooltip>
        </div>

        {/* Conversation list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {loadingConvs ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <Spin size="small" />
            </div>
          ) : conversations.length === 0 ? (
            !siderCollapsed && (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无历史对话"
                style={{ padding: '32px 0' }}
              />
            )
          ) : (
            <List
              dataSource={conversations}
              renderItem={(conv) => {
                const isActive = conv.id === activeId
                return (
                  <List.Item
                    key={conv.id}
                    style={{
                      padding: '8px',
                      marginBottom: 2,
                      borderRadius: 8,
                      cursor: 'pointer',
                      background: isActive ? '#e6f4ff' : 'transparent',
                      border: isActive ? '1px solid #bae0ff' : '1px solid transparent',
                      transition: 'all 0.15s',
                    }}
                    onClick={() => openConversation(conv.id)}
                  >
                    {siderCollapsed ? (
                      <Tooltip title={conversationTitle(conv)} placement="right">
                        <Badge count={conv.message_count} size="small" color="#1677ff">
                          <Avatar
                            size={28}
                            style={{ background: isActive ? '#1677ff' : '#d9d9d9' }}
                            icon={<RobotOutlined />}
                          />
                        </Badge>
                      </Tooltip>
                    ) : (
                      <div
                        style={{
                          display: 'flex',
                          width: '100%',
                          alignItems: 'center',
                          gap: 6,
                          overflow: 'hidden',
                        }}
                      >
                        <div style={{ flex: 1, overflow: 'hidden' }}>
                          <Text
                            ellipsis
                            style={{
                              fontSize: 13,
                              fontWeight: isActive ? 600 : 400,
                              color: isActive ? '#1677ff' : '#333',
                              display: 'block',
                            }}
                          >
                            {conversationTitle(conv)}
                          </Text>
                          <Text
                            type="secondary"
                            style={{ fontSize: 11, display: 'block' }}
                          >
                            {formatTime(conv.updated_at)} · {conv.message_count} 条
                          </Text>
                        </div>
                        <Dropdown
                          menu={{
                            items: [
                              {
                                key: 'delete',
                                icon: <DeleteOutlined />,
                                label: '删除',
                                danger: true,
                                onClick: ({ domEvent }) => {
                                  domEvent.stopPropagation()
                                  handleDelete(conv)
                                },
                              },
                            ],
                          }}
                          trigger={['click']}
                        >
                          <Button
                            size="small"
                            type="text"
                            icon={<EllipsisOutlined />}
                            style={{ flexShrink: 0 }}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Dropdown>
                      </div>
                    )}
                  </List.Item>
                )
              }}
            />
          )}
        </div>

        {/* User info + logout */}
        <div
          style={{
            padding: siderCollapsed ? '12px 8px' : '12px 16px',
            borderTop: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            justifyContent: siderCollapsed ? 'center' : 'flex-start',
          }}
        >
          <Avatar size={32} icon={<UserOutlined />} style={{ background: '#1677ff', flexShrink: 0 }} />
          {!siderCollapsed && (
            <>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <Text strong ellipsis style={{ fontSize: 13, display: 'block' }}>
                  {user?.display_name ?? user?.username ?? '用户'}
                </Text>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {user?.dept_name ?? '系统'}
                </Text>
              </div>
              <Tooltip title="个人设置">
                <Button
                  size="small"
                  type="text"
                  icon={<SettingOutlined />}
                  onClick={() => setSettingsOpen(true)}
                />
              </Tooltip>
              {(user?.role === 'super_admin' || user?.role === 'dept_admin') && (
                <Tooltip title="管理后台">
                  <Button
                    size="small"
                    type="text"
                    icon={<DashboardOutlined />}
                    onClick={() => navigate('/admin')}
                  />
                </Tooltip>
              )}
              <Tooltip title="退出登录">
                <Button
                  size="small"
                  type="text"
                  icon={<LogoutOutlined />}
                  onClick={handleLogout}
                />
              </Tooltip>
            </>
          )}
        </div>
      </Sider>

      {/* ── Personal settings modal ───────────────────────────── */}
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* ── Chat area ─────────────────────────────────────────── */}
      <Content
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          background: '#fafafa',
        }}
      >
        {/* Top bar */}
        <div
          style={{
            padding: '0 24px',
            height: 56,
            display: 'flex',
            alignItems: 'center',
            borderBottom: '1px solid #f0f0f0',
            background: '#fff',
            flexShrink: 0,
          }}
        >
          <Text strong style={{ fontSize: 15 }}>
            {activeId
              ? (conversations.find((c) => c.id === activeId)
                  ? conversationTitle(conversations.find((c) => c.id === activeId)!)
                  : '加载中…')
              : '新对话'}
          </Text>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 0' }}>
          {loadingMsgs ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin tip="加载消息中…" />
            </div>
          ) : messages.length === 0 ? (
            <div
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#aaa',
                gap: 12,
              }}
            >
              <RobotOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />
              <Text type="secondary" style={{ fontSize: 15 }}>
                有什么可以帮你的？
              </Text>
              <Text type="secondary" style={{ fontSize: 13 }}>
                基于企业知识库回答，支持文档检索与引用
              </Text>
            </div>
          ) : (
            <div style={{ maxWidth: 800, margin: '0 auto', padding: '0 24px' }}>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input box */}
        <div
          style={{
            padding: '16px 24px',
            background: '#fff',
            borderTop: '1px solid #f0f0f0',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              maxWidth: 800,
              margin: '0 auto',
              display: 'flex',
              gap: 10,
              alignItems: 'flex-end',
            }}
          >
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入问题，Enter 发送，Shift+Enter 换行…"
              autoSize={{ minRows: 1, maxRows: 6 }}
              style={{ borderRadius: 10, resize: 'none', fontSize: 14 }}
              disabled={streaming}
            />
            {streaming ? (
              <Button
                danger
                icon={<CloseCircleOutlined />}
                size="large"
                onClick={() => {
                  if (abortRef.current) {
                    abortRef.current.abort()
                  }
                }}
                style={{ borderRadius: 10, height: 40, paddingInline: 18 }}
              >
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                size="large"
                disabled={!inputValue.trim()}
                onClick={() => sendMessage()}
                style={{ borderRadius: 10, height: 40, paddingInline: 18 }}
              >
                发送
              </Button>
            )}
          </div>
          <div style={{ maxWidth: 800, margin: '4px auto 0', textAlign: 'right' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {streaming ? '正在生成回答…' : 'Enter 发送'}
            </Text>
            {showRetry && (
              <Button
                type="link"
                size="small"
                onClick={handleRetry}
                style={{ fontSize: 11, padding: 0, marginLeft: 8 }}
              >
                响应较慢，点击重试
              </Button>
            )}
          </div>
        </div>
      </Content>
    </Layout>
  )
}

// ─── MessageBubble sub-component ──────────────────────────────────

function MessageBubble({ msg }: { msg: UiMessage }) {
  const isUser = msg.role === 'user'

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        gap: 10,
        marginBottom: 20,
        alignItems: 'flex-start',
      }}
    >
      {/* Avatar */}
      <Avatar
        size={36}
        icon={isUser ? <UserOutlined /> : <RobotOutlined />}
        style={{
          background: isUser ? '#1677ff' : '#52c41a',
          flexShrink: 0,
        }}
      />

      {/* Bubble */}
      <div style={{ maxWidth: '78%' }}>
        <div
          style={{
            background: isUser ? '#1677ff' : '#fff',
            color: isUser ? '#fff' : '#1a1a1a',
            padding: '10px 14px',
            borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
            fontSize: 14,
            lineHeight: 1.7,
            wordBreak: 'break-word',
          }}
        >
          {!msg.content && msg.streaming ? (
            <span style={{ color: '#52c41a' }}>
              <LoadingOutlined style={{ marginRight: 6 }} />
              {msg.sources ? '已找到相关资料，正在生成回答…' : '思考中…'}
            </span>
          ) : isUser ? (
            <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
          ) : (
            <div className="md-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
          )}
          {msg.streaming && msg.content && (
            <span
              style={{
                display: 'inline-block',
                width: 2,
                height: 14,
                background: '#52c41a',
                marginLeft: 2,
                verticalAlign: 'middle',
                animation: 'blink 1s step-start infinite',
              }}
            />
          )}
        </div>

        {/* Tool Calls */}
        {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
          <div style={{ marginTop: 6 }}>
            {msg.toolCalls.map((tc, i) => (
              <ToolCallCard key={i} info={tc} />
            ))}
          </div>
        )}

        {/* Sources */}
        {!isUser && msg.sources && msg.sources.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <SourceCard sources={msg.sources} />
          </div>
        )}
      </div>
    </div>
  )
}
