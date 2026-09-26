import type { ChatMessage } from '@/types'
import clsx from 'clsx'
import CitationList from './CitationList'
import RatingButtons from './RatingButtons'
import { useChatStore } from '@/store/chatStore'

interface Props {
  message: ChatMessage
}

export default function MessageBubble({ message }: Props) {
  const rateMessage = useChatStore((s) => s.rateMessage)
  const isUser = message.role === 'user'

  return (
    <div className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[85%] rounded-xl px-4 py-3 text-sm',
          isUser
            ? 'bg-accent text-white rounded-br-sm'
            : 'bg-surface border border-border rounded-bl-sm'
        )}
      >
        {/* Message content */}
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

        {/* Citations (assistant only) */}
        {!isUser && message.cited_records && message.cited_records.length > 0 && (
          <CitationList records={message.cited_records} />
        )}

        {/* Footer row */}
        {!isUser && (
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/60">
            {message.latency_ms !== undefined && (
              <span className="text-[11px] text-muted">
                {(message.latency_ms / 1000).toFixed(1)}s
              </span>
            )}
            <RatingButtons
              messageId={message.id}
              current={message.helpful ?? null}
              onRate={rateMessage}
            />
          </div>
        )}
      </div>
    </div>
  )
}
