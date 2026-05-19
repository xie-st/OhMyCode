import { EmptyState } from '../components/EmptyState'
import { MessageList } from '../components/MessageList'
import { useAppStore } from '../state/store'

export function WindowA() {
  const messages = useAppStore((state) => state.messagesA)
  const isATurnActive = useAppStore((state) => state.isATurnActive)

  return (
    <section className="flex h-full flex-col bg-stone-50">
      {messages.length === 0 && !isATurnActive ? (
        <EmptyState title="Window A" accent="emerald" />
      ) : (
        <MessageList messages={messages} showSpinner={isATurnActive} spinnerLabel="Thinking" />
      )}
    </section>
  )
}

export default WindowA
