import { EmptyState } from '../components/EmptyState'
import { MessageList } from '../components/MessageList'
import { useAppStore } from '../state/store'

export function WindowB() {
  const messagesB = useAppStore((state) => state.messagesB)
  const bTrigger = useAppStore((state) => state.bTrigger)

  return (
    <section className="flex h-full flex-col bg-white text-stone-900">
      {bTrigger && (
        <div className="shrink-0 border-b border-pink-100 bg-pink-50 px-4 py-2 font-mono text-xs text-pink-700">
          B active: {bTrigger}
        </div>
      )}
      {messagesB.length === 0 ? (
        <EmptyState title="Window B" accent="pink" />
      ) : (
        <MessageList messages={messagesB} tone="pink" />
      )}
    </section>
  )
}

export default WindowB
