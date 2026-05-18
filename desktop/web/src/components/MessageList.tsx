import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import type { Message } from '../state/store'

interface MessageListProps {
  messages: Message[]
  role?: 'all' | 'assistant-only'
  tone?: 'dark' | 'amber'
}

export function MessageList({ messages, role = 'all', tone = 'dark' }: MessageListProps) {
  const visibleMessages =
    role === 'assistant-only'
      ? messages.filter((message) => message.role === 'assistant')
      : messages

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        {visibleMessages.length === 0 && (
          <div
            className={
              tone === 'amber'
                ? 'pt-8 text-sm text-stone-500'
                : 'pt-8 text-sm text-zinc-500'
            }
          >
            {tone === 'amber' ? 'Waiting for a safe moment...' : 'No messages yet.'}
          </div>
        )}
        {visibleMessages.map((message) => (
          <MessageBubble key={message.id} message={message} tone={tone} />
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message, tone }: { message: Message; tone: 'dark' | 'amber' }) {
  const assistantClass =
    tone === 'amber'
      ? 'w-full text-sm leading-6 text-stone-900'
      : 'w-full text-sm leading-6 text-zinc-100'
  const userClass =
    tone === 'amber'
      ? 'self-end rounded border border-amber-300 bg-amber-100 px-3 py-2 text-sm text-stone-900'
      : 'self-end rounded border border-emerald-700 bg-emerald-950 px-3 py-2 text-sm text-emerald-50'

  return (
    <article className={message.role === 'user' ? userClass : assistantClass}>
      {message.role === 'assistant' ? (
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{message.text || ' '}</ReactMarkdown>
      ) : (
        message.text
      )}

      {message.toolCalls?.map((tool) => (
        <div
          key={tool.id}
          className={
            tone === 'amber'
              ? 'mt-3 rounded border border-amber-200 bg-white p-3 text-xs text-stone-700'
              : 'mt-3 rounded border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300'
          }
        >
          <div
            className={
              tone === 'amber' ? 'font-medium text-amber-800' : 'font-medium text-cyan-300'
            }
          >
            {tool.name}
          </div>
          <pre className={tone === 'amber' ? 'mt-2 text-stone-500' : 'mt-2 text-zinc-400'}>
            {JSON.stringify(tool.params, null, 2)}
          </pre>
          {tool.result !== undefined && (
            <pre className={tool.isError ? 'mt-2 text-red-600' : 'mt-2 text-inherit'}>
              {tool.result}
            </pre>
          )}
        </div>
      ))}
    </article>
  )
}
