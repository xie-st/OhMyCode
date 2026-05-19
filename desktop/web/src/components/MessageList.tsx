import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import { Spinner } from './Spinner'
import type { AssistantSegment, Message, ToolCall } from '../state/store'

interface MessageListProps {
  messages: Message[]
  role?: 'all' | 'assistant-only'
  tone?: 'dark' | 'amber'
  showSpinner?: boolean
  spinnerLabel?: string
}

export function MessageList({
  messages,
  role = 'all',
  tone = 'dark',
  showSpinner = false,
  spinnerLabel = 'Thinking',
}: MessageListProps) {
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
        {showSpinner && <Spinner label={spinnerLabel} />}
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
        <AssistantContent message={message} tone={tone} />
      ) : (
        message.text
      )}

      {message.error && (
        <details className="mt-2 text-xs text-rose-400">
          <summary className="cursor-pointer">Error details</summary>
          <pre className="mt-1 whitespace-pre-wrap font-mono">{message.error}</pre>
        </details>
      )}
    </article>
  )
}

function AssistantContent({ message, tone }: { message: Message; tone: 'dark' | 'amber' }) {
  const segments = message.segments ?? [{ kind: 'text' as const, text: message.text }]

  return (
    <>
      {segments.map((segment, index) => (
        <AssistantSegmentView
          key={`${segment.kind}-${index}`}
          segment={segment}
          tone={tone}
        />
      ))}
    </>
  )
}

function AssistantSegmentView({
  segment,
  tone,
}: {
  segment: AssistantSegment
  tone: 'dark' | 'amber'
}) {
  if (segment.kind === 'text') {
    return <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{segment.text || ' '}</ReactMarkdown>
  }

  return <ToolCallCard tool={segment.tool} tone={tone} />
}

function ToolCallCard({ tool, tone }: { tool: ToolCall; tone: 'dark' | 'amber' }) {
  return (
    <div
      className={
        tone === 'amber'
          ? 'my-3 rounded border border-amber-200 bg-white p-3 text-xs text-stone-700'
          : 'my-3 rounded border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300'
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
        {formatParams(tool)}
      </pre>
      <ToolResult tool={tool} tone={tone} />
    </div>
  )
}

function ToolResult({ tool, tone }: { tool: ToolCall; tone: 'dark' | 'amber' }) {
  const [expanded, setExpanded] = useState(false)
  if (tool.result === undefined && tool.resultPreview === undefined) {
    return null
  }
  // Preview comes from the server (desktop/server/render_rules.py); fall back
  // to raw result only if the server somehow didn't send a preview.
  const preview = tool.resultPreview ?? tool.result ?? ''
  const fullText = tool.result ?? preview
  const shown = expanded ? fullText : preview
  const totalLines = fullText.split('\n').length
  const resultClass = tool.isError
    ? 'mt-2 whitespace-pre-wrap text-red-600'
    : tone === 'amber'
      ? 'mt-2 whitespace-pre-wrap text-stone-700'
      : 'mt-2 whitespace-pre-wrap text-zinc-300'

  return (
    <div>
      <pre className={resultClass}>{`${tool.isError ? 'Error' : 'Result'}\n${shown}`}</pre>
      {tool.isTruncated && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className={tone === 'amber' ? 'mt-2 text-xs text-amber-700' : 'mt-2 text-xs text-cyan-300'}
        >
          {expanded ? 'Collapse' : `Show more (${totalLines} lines)`}
        </button>
      )}
    </div>
  )
}

function formatParams(tool: ToolCall) {
  // Server-rendered preview (render_rules.py truncate_params) is the single
  // source of truth; fall back to a local JSON dump only if it's missing.
  return tool.paramsPreview ?? JSON.stringify(tool.params)
}
