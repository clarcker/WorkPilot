// ── Auth ─────────────────────────────────────────────────────────

// What gets stored in localStorage after login (flattened for convenience)
export interface StoredAuth {
  access_token: string
  must_change_password: boolean
  id: number
  username: string
  display_name: string
  real_name: string
  role: 'super_admin' | 'dept_admin' | 'employee'
  dept_id: number | null
  dept_name: string | null
  dept_code: string | null
}

// ── Chat ─────────────────────────────────────────────────────────

export interface Conversation {
  id: number
  title: string | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface Source {
  doc_id: number
  doc_name: string
  chunk_id: number
  heading: string | null
  page_no: number | null
  score: number
  chunk_text: string
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources: Source[] | null
  created_at: string
}

export interface ConversationDetail {
  conversation: {
    id: number
    title: string | null
    status: string
    message_count: number
    created_at: string
    updated_at: string
  }
  messages: Message[]
}

// ── SSE event payloads ────────────────────────────────────────────

export interface ToolCallInfo {
  tool_name: string
  tool_args: Record<string, unknown>
  allowed: boolean
  deny_reason?: string
  result?: unknown
  error?: string
  latency_ms?: number
}

export type SSEEvent =
  | { type: 'conversation_id'; content: number }
  | { type: 'token';           content: string }
  | { type: 'sources';         content: Source[] }
  | { type: 'tool_call';       content: ToolCallInfo }
  | { type: 'done';            content: string }
  | { type: 'error';           content: string }
