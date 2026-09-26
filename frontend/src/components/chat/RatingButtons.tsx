import clsx from 'clsx'

interface Props {
  messageId: string
  current: boolean | null
  onRate: (id: string, helpful: boolean) => Promise<void>
}

export default function RatingButtons({ messageId, current, onRate }: Props) {
  return (
    <div className="flex items-center gap-1 ml-auto">
      <button
        onClick={() => onRate(messageId, true)}
        title="Helpful"
        className={clsx(
          'text-base leading-none transition-opacity',
          current === true ? 'opacity-100' : 'opacity-30 hover:opacity-70'
        )}
      >
        👍
      </button>
      <button
        onClick={() => onRate(messageId, false)}
        title="Not helpful"
        className={clsx(
          'text-base leading-none transition-opacity',
          current === false ? 'opacity-100' : 'opacity-30 hover:opacity-70'
        )}
      >
        👎
      </button>
    </div>
  )
}
