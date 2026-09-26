/**
 * Chat store — manages the active chat session and message thread.
 * Streaming tokens are accumulated here before being committed as messages.
 */
import { create } from 'zustand'
import type { ChatMessage, CitedRecord } from '@/types'
import { chatApi } from '@/api'

function generateId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2)
}

interface ChatState {
  sessionId: string | null
  messages: ChatMessage[]
  isLoading: boolean
  streamingContent: string        // accumulates tokens during a stream
  error: string | null

  // Actions
  ask: (question: string, filters?: { service_name?: string; environment?: string }) => Promise<void>
  appendToken: (token: string) => void
  commitStream: (messageId: string, citedRecords: CitedRecord[]) => void
  rateMessage: (messageId: string, helpful: boolean) => Promise<void>
  startNewSession: () => void
  clearError: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  messages: [],
  isLoading: false,
  streamingContent: '',
  error: null,

  ask: async (question, filters) => {
    const userMessageId = generateId()

    set((s) => ({
      isLoading: true,
      error: null,
      streamingContent: '',
      messages: [
        ...s.messages,
        { id: userMessageId, role: 'user', content: question },
      ],
    }))

    try {
      const resp = await chatApi.ask({
        question,
        session_id: get().sessionId ?? undefined,
        ...filters,
      })

      set((s) => ({
        sessionId: resp.session_id,
        isLoading: false,
        messages: [
          ...s.messages,
          {
            id: resp.message_id,
            role: 'assistant',
            content: resp.answer,
            cited_records: resp.cited_records,
            latency_ms: resp.latency_ms,
            helpful: null,
          },
        ],
      }))
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Something went wrong.',
      })
    }
  },

  appendToken: (token) =>
    set((s) => ({ streamingContent: s.streamingContent + token })),

  commitStream: (messageId, citedRecords) =>
    set((s) => ({
      isLoading: false,
      streamingContent: '',
      messages: [
        ...s.messages,
        {
          id: messageId,
          role: 'assistant',
          content: s.streamingContent,
          cited_records: citedRecords,
          helpful: null,
        },
      ],
    })),

  rateMessage: async (messageId, helpful) => {
    await chatApi.rate(messageId, helpful)
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === messageId ? { ...m, helpful } : m
      ),
    }))
  },

  startNewSession: () =>
    set({ sessionId: null, messages: [], streamingContent: '', error: null }),

  clearError: () => set({ error: null }),
}))
