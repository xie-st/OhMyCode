import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import type { BCard } from '../state/store'
import { useAppStore } from '../state/store'
import { Spinner } from './Spinner'

interface BCardStackProps {
  cards: BCard[]
  isBTurnActive: boolean
}

export function BCardStack({ cards, isBTurnActive }: BCardStackProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
        {cards.map((card) => (
          <CardView key={card.id} card={card} />
        ))}
        {isBTurnActive && (
          <Spinner label="Thinking" className="text-pink-600" />
        )}
      </div>
    </div>
  )
}

function CardView({ card }: { card: BCard }) {
  const acceptBQuestion = useAppStore((s) => s.acceptBQuestion)
  const reactivateStaleCard = useAppStore((s) => s.reactivateStaleCard)

  if (card.state === 'expanded') {
    // Render as a transcript: B's question -> user's "好的，聊聊" -> expansion.
    // This matches the shape that gets persisted to loop_b once the user
    // accepts: assistant(question) / user("好的，聊聊") / assistant(expansion).
    return (
      <article className="flex flex-col gap-3">
        <div className="text-[15px] leading-7 text-stone-900">{card.question}</div>
        <div className="font-mono text-sm text-stone-700">
          <span className="text-pink-500">{'>'}</span> 好的，聊聊
        </div>
        <div className="prose max-w-none text-[15px] leading-7 text-stone-900">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {card.expansion ?? ''}
          </ReactMarkdown>
        </div>
      </article>
    )
  }

  if (card.state === 'stale') {
    return (
      <button
        type="button"
        onClick={() => reactivateStaleCard(card.id)}
        className="rounded-xl border border-stone-200 bg-stone-100 p-3 text-left text-sm text-stone-400 transition hover:bg-stone-50 hover:text-stone-600"
        title="点这里重新激活这个问题"
      >
        {card.question}
      </button>
    )
  }

  // pending
  return (
    <article className="rounded-xl border border-pink-200 bg-pink-50 p-4 shadow-sm">
      <div className="text-[15px] leading-7 text-stone-900">{card.question}</div>
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={card.awaitingExpansion}
          onClick={() => acceptBQuestion(card.id)}
          className="rounded-full bg-pink-500 px-3 py-1 text-xs font-medium text-white hover:bg-pink-600 disabled:cursor-not-allowed disabled:bg-pink-300"
        >
          {card.awaitingExpansion ? '小柚 正在准备…' : '聊聊'}
        </button>
      </div>
    </article>
  )
}

export default BCardStack
