/**
 * Feed store — real-time agent feed entries.
 * New entries arrive via WebSocket; historical entries are fetched via REST.
 */
import { create } from 'zustand'
import type { FeedEntry } from '@/types'
import { feedApi } from '@/api'

interface FeedState {
  entries: FeedEntry[]
  total: number
  unreadCount: number
  isLoading: boolean

  // Actions
  fetchFeed: (params?: { limit?: number; offset?: number; unread_only?: boolean }) => Promise<void>
  fetchUnread: () => Promise<void>
  prependEntry: (entry: FeedEntry) => void      // called by WS handler
  markRead: (entryId: number) => Promise<void>
  markAllRead: () => void
}

export const useFeedStore = create<FeedState>((set, get) => ({
  entries: [],
  total: 0,
  unreadCount: 0,
  isLoading: false,

  fetchFeed: async (params) => {
    set({ isLoading: true })
    try {
      const resp = await feedApi.getFeed(params)
      set({
        entries: params?.offset
          ? [...get().entries, ...resp.entries]  // pagination append
          : resp.entries,
        total: resp.total,
        isLoading: false,
      })
    } catch {
      set({ isLoading: false })
    }
  },

  fetchUnread: async () => {
    try {
      const resp = await feedApi.getUnread()
      set({ unreadCount: resp.unread })
    } catch {
      // non-critical
    }
  },

  prependEntry: (entry) =>
    set((s) => ({
      entries: [entry, ...s.entries],
      total: s.total + 1,
      unreadCount: s.unreadCount + 1,
    })),

  markRead: async (entryId) => {
    await feedApi.markRead(entryId)
    set((s) => ({
      entries: s.entries.map((e) =>
        e.id === entryId ? { ...e, is_read: true } : e
      ),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }))
  },

  markAllRead: () =>
    set((s) => ({
      entries: s.entries.map((e) => ({ ...e, is_read: true })),
      unreadCount: 0,
    })),
}))
