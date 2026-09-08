import client from './client'
import type { Conversation, ConversationDetail, SSEEvent } from '../types'

// ── Conversations ─────────────────────────────────────────────────

interface PagedConversations {
  items: Conversation[]
  total: number
  page: number
  page_size: number
}

export async function listConversations(page = 1, pageSize = 50): Promise<Conversation[]> {
  const { data } = await client.get<PagedConversations>('/chat/conversations', {
    params: { page, page_size: pageSize },
  })
  return data.items
}

export async function getConversation(id: number): Promise<ConversationDetail> {
  const { data } = await client.get<ConversationDetail>(`/chat/conversations/${id}`)
  return data
}

export async function deleteConversation(id: number): Promise<void> {
  await client.delete(`/chat/conversations/${id}`)
}

// ── SSE streaming ─────────────────────────────────────────────────
// EventSource only supports GET; we use fetch + ReadableStream for POST.

export function streamChat(
  query: string,
  conversationId: number | null,
  onEvent: (event: SSEEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('access_token') ?? ''

  return fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, conversation_id: conversationId }),
    signal,
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`HTTP ${res.status}: ${text}`)
    }
    if (!res.body) throw new Error('No response body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE lines are separated by \n\n (one event) or \n (within event)
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''   // keep incomplete last line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          const evt = JSON.parse(raw) as SSEEvent
          onEvent(evt)
        } catch {
          // ignore malformed lines
        }
      }
    }
  })
}
