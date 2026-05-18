import { FormEvent, KeyboardEvent, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAppStore } from '../state/store'

const statusLabel = {
  connecting: 'Connecting',
  open: 'Open',
  closed: 'Closed',
  error: 'Error',
}

export default function WindowA() {
  const [draft, setDraft] = useState('')
  const messages = useAppStore((state) => state.messages)
  const status = useAppStore((state) => state.status)
  const { sendMessage, cancel } = useWebSocket()

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    sendMessage(draft)
    setDraft('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
    if (event.key === 'Escape') {
      cancel()
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-800 px-4">
        <h1 className="text-sm font-semibold tracking-normal text-zinc-100">Window A</h1>
        <span className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300">
          {statusLabel[status]}
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
          {messages.map((message) => (
            <article
              key={message.id}
              className={
                message.role === 'user'
                  ? 'self-end rounded border border-emerald-700 bg-emerald-950 px-3 py-2 text-sm text-emerald-50'
                  : 'w-full text-sm leading-6 text-zinc-100'
              }
            >
              {message.role === 'assistant' ? (
                <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                  {message.text || ' '}
                </ReactMarkdown>
              ) : (
                message.text
              )}

              {message.toolCalls?.map((tool) => (
                <div
                  key={tool.id}
                  className="mt-3 rounded border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300"
                >
                  <div className="font-medium text-cyan-300">{tool.name}</div>
                  <pre className="mt-2 text-zinc-400">
                    {JSON.stringify(tool.params, null, 2)}
                  </pre>
                  {tool.result !== undefined && (
                    <pre className={tool.isError ? 'mt-2 text-red-300' : 'mt-2 text-zinc-200'}>
                      {tool.result}
                    </pre>
                  )}
                </div>
              ))}
            </article>
          ))}
        </div>
      </div>

      <form onSubmit={submit} className="shrink-0 border-t border-zinc-800 p-4">
        <div className="mx-auto flex max-w-4xl gap-2">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            rows={3}
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
