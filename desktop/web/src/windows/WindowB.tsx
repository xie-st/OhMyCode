import { BCardStack } from '../components/BCardStack'
import { EmptyState } from '../components/EmptyState'
import { MessageList } from '../components/MessageList'
import { useAppStore } from '../state/store'

export function WindowB() {
  const messagesB = useAppStore((state) => state.messagesB)
  const bCards = useAppStore((state) => state.bCards)
  const bTrigger = useAppStore((state) => state.bTrigger)
  const isBTurnActive = useAppStore((state) => state.isBTurnActive)

  const hasCards = bCards.length > 0
  const hasHistory = messagesB.length > 0

  return (
    <section className="flex h-full flex-col bg-white text-stone-900">
      {bTrigger && (
        <div className="shrink-0 border-b border-pink-100 bg-pink-50 px-4 py-2 font-mono text-xs text-pink-700">
          B active: {bTrigger}
        </div>
      )}
      {hasCards ? (
        <BCardStack cards={bCards} isBTurnActive={isBTurnActive} />
      ) : hasHistory ? (
        <MessageList
          messages={messagesB}
          tone="pink"
          showSpinner={isBTurnActive}
          spinnerLabel="Thinking"
        />
      ) : isBTurnActive ? (
        <BCardStack cards={[]} isBTurnActive={true} />
      ) : (
        <EmptyState title="Window B" accent="pink" />
      )}
    </section>
  )
}

export default WindowB
