/**
 * MessageBubble — 单条对话气泡（用户 / 助手）
 * 含 Markdown 渲染、流式光标、工具卡片、引用来源、确认卡、缺槽提示。
 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Avatar } from 'antd'
import {
  RobotOutlined,
  UserOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import SourceCard from './SourceCard'
import ToolCallCard from './ToolCallCard'
import ConfirmCard, { FormIncompleteBanner } from './ConfirmCard'
import type {
  Source,
  ToolCallInfo,
  ConfirmRequiredPayload,
  FormIncompletePayload,
} from '../types'

export interface UiMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  toolCalls?: ToolCallInfo[]
  confirm?: ConfirmRequiredPayload
  formIncomplete?: FormIncompletePayload
  streaming?: boolean
}

export default function MessageBubble({
  msg,
  onConfirmDone,
}: {
  msg: UiMessage
  onConfirmDone?: (action: 'confirmed' | 'cancelled', text: string) => void
}) {
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
      <Avatar
        size={36}
        icon={isUser ? <UserOutlined /> : <RobotOutlined />}
        style={{
          background: isUser ? '#1677ff' : '#52c41a',
          flexShrink: 0,
        }}
      />

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

        {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
          <div style={{ marginTop: 6 }}>
            {msg.toolCalls.map((tc, i) => (
              <ToolCallCard key={i} info={tc} />
            ))}
          </div>
        )}

        {!isUser && msg.formIncomplete && (
          <FormIncompleteBanner
            slots={msg.formIncomplete.missing_slots || []}
            message={msg.formIncomplete.message}
          />
        )}

        {!isUser && msg.confirm && (
          <ConfirmCard data={msg.confirm} onDone={onConfirmDone} />
        )}

        {!isUser && msg.sources && msg.sources.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <SourceCard sources={msg.sources} />
          </div>
        )}
      </div>
    </div>
  )
}
