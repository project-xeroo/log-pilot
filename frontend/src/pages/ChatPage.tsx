import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '@/store/chatStore'
import MessageBubble from '@/components/chat/MessageBubble'

// Suggested prompts for the Junior Engineer guided mode (PRD §9.3)
const SUGGESTED_PROMPTS = [
  'Why is the error rate spiking right now?',
  'What happened during the last deployment?',
  'Show me all CRITICAL errors in the last hour.',
  'Which service is causing the most failures?',
  'Explain this error: connection pool exhausted.',
  'What are the leading indicators of a failure for payment-service?',
]

export default function ChatPage() {
  const { messages, isLoading, error, ask, startNewSession } = useChatStore()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = input.trim()
    if (!q || isLoading) return
    setInput('')
    ask(q)
  }

  const handleSuggestion = (prompt: string) => {
    ask(prompt)
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
        <div>
          <h1 className="text-base font-semibold">Chat</h1>
          <p className="text-xs text-muted">Ask a question about your logs</p>
        </div>
        {!isEmpty && (
          <button
            onClick={startNewSession}
            className="text-xs text-muted hover:text-accent transition-colors"
          >
            + New session
          </button>
        )}
      </div>

      {/* Message thread */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {isEmpty ? (
          <div className="h-full flex flex-col items-center justify-center">
            <p className="text-4xl mb-3">💬</p>
            <p className="font-medium text-[15px] mb-1">Ask LogPilot anything</p>
            <p className="text-sm text-muted mb-8 text-center max-w-sm">
              Get sourced, evidence-backed answers about your production logs.
            </p>
            {/* Suggested prompts */}
            <div className="w-full max-w-xl grid grid-cols-1 gap-2">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSuggestion(prompt)}
                  className="text-left text-sm px-4 py-2.5 rounded-lg border border-border hover:border-accent/50 hover:bg-accent/5 transition-colors text-[#1f2328]"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}

            {/* Streaming indicator */}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-surface border border-border rounded-xl rounded-bl-sm px-4 py-3">
                  <span className="text-sm text-muted animate-pulse">Thinking…</span>
                </div>
              </div>
            )}

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                {error}
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 px-6 py-4 border-t border-border">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question…"
            disabled={isLoading}
            className="flex-1 border border-border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="bg-accent text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
          >
            Ask
          </button>
        </form>
      </div>
    </div>
  )
}
