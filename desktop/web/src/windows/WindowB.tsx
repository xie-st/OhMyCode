import { MessageList } from '../components/MessageList'
import { useAppStore } from '../state/store'

export function WindowB() {
  const messagesB = useAppStore((state) => state.messagesB)
  const bTrigger = useAppStore((state) => state.bTrigger)
  const status = useAppStore((state) => state.status)

  return (
    <section className="flex h-full flex-col bg-amber-50 text-stone-900">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-amber-200 px-3 py-2 text-xs text-stone-600">
        <span className="font-medium text-stone-800">小柚 · 成长伙伴</span>
        <div className="flex items-center gap-3">
          {bTrigger && <span className="text-amber-700">正在被触发：{bTrigger}</span>}
          <span className="text-stone-500">{status}</span>
        </div>
      </header>
      <MessageList messages={messagesB} role="assistant-only" tone="amber" />
    </section>
  )
}

export default WindowB
