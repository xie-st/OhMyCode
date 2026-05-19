import { FormEvent, KeyboardEvent, useState } from 'react'
import { MessageList } from '../components/MessageList'
import { useAppStore } from '../state/store'

const statusLabel = {
  connecting: 'Connecting',
  open: 'Open',
  closed: 'Closed',
  error: 'Error',
}

interface WindowAProps {
  sendMessage(text: string): void
  sendUserTyping(typing: boolean): void
}

export function WindowA({ sendMessage, sendUserTyping }: WindowAProps) {
  const [draft, setDraft] = useState('')
  const [focused, setFocused] = useState(false)
  const messages = useAppStore((state) => state.messagesA)
  const status = useAppStore((state) => state.status)
  const isATurnActive = useAppStore((state) => state.isATurnActive)

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    sendMessage(draft)
    setDraft('')
    if (!focused) {
      sendUserTyping(false)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <section className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-800 px-4">
        <h1 className="text-sm font-semibold tracking-normal text-zinc-100">Window A</h1>
        <span className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300">
          {statusLabel[status]}
        </span>
      </header>

      <MessageList messages={messages} showSpinner={isATurnActive} spinnerLabel="Thinking" />

      <form onSubmit={submit} className="shrink-0 border-t border-zinc-800 p-4">
        <div className="mx-auto flex max-w-4xl gap-2">
          <textarea
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              if (focused) {
                sendUserTyping(true)
              }
            }}
            onFocus={() => {
              setFocused(true)
              sendUserTyping(true)
            }}
            onBlur={() => {
              setFocused(false)
              sendUserTyping(false)
            }}
            onKeyDown={onKeyDown}
            rows={3}
            placeholder="Ask OhMyCode to inspect, edit, or explain the project..."
            className="min-h-20 flex-1 resize-none rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
          />
          <button
            type="submit"
            disabled={status !== 'open' || !draft.trim()}
            className="h-20 w-24 rounded bg-cyan-600 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-zinc-700"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  )
}

export default WindowA
