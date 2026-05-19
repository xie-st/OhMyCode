import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import type { AssistantSegment, Message, ToolCall } from '../state/store'
import { Spinner } from './Spinner'

interface MessageListProps {
  messages: Message[]
  tone?: 'emerald' | 'pink'
  showSpinner?: boolean
  spinnerLabel?: string
}

export function MessageList({
  messages,
  tone = 'emerald',
  showSpinner = false,
  spinnerLabel = 'Thinking',
}: MessageListProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} tone={tone} />
        ))}
        {showSpinner && (
          <Spinner
            label={spinnerLabel}
            className={tone === 'pink' ? 'text-pink-600' : 'text-emerald-600'}
          />
        )}
      </div>
    </div>
  )
}

function MessageBubble({ message, tone }: { message: Message; tone: 'emerald' | 'pink' }) {
  const marker = tone === 'emerald' ? 'text-emerald-600' : 'text-pink-600'

  return (
    <article className="w-full text-sm leading-7 text-stone-900">
      {message.role === 'assistant' ? (
        <AssistantContent message={message} tone={tone} />
      ) : (
        <div className="font-mono text-sm text-stone-700">
          <span className={marker}>{'>'}</span> {message.text}
        </div>
      )}

      {message.error && (
        <details className="mt-2 text-xs text-pink-700">
          <summary className="cursor-pointer">Error details</summary>
          <pre className="mt-1 whitespace-pre-wrap font-mono">{message.error}</pre>
        </details>
      )}
    </article>
  )
}

function AssistantContent({ message, tone }: { message: Message; tone: 'emerald' | 'pink' }) {
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
  tone: 'emerald' | 'pink'
}) {
  if (segment.kind === 'text') {
    return (
      <div className="prose max-w-none text-[15px] leading-7 text-stone-900">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{segment.text || ' '}</ReactMarkdown>
      </div>
    )
  }

  return <ToolCallCard tool={segment.tool} tone={tone} />
}

function ToolCallCard({ tool, tone }: { tool: ToolCall; tone: 'emerald' | 'pink' }) {
  const border = toolBorderClass(tool, tone)

  return (
    <div className={`my-3 rounded-xl border border-stone-200 border-l-2 ${border} bg-white p-3 text-xs text-stone-700 shadow-sm`}>
      <div className="font-mono font-medium text-stone-900">{tool.name}</div>
      <pre className="mt-2 text-stone-500">{formatParams(tool)}</pre>
      <ToolResult tool={tool} tone={tone} />
    </div>
  )
}

function ToolResult({ tool, tone }: { tool: ToolCall; tone: 'emerald' | 'pink' }) {
  const [expanded, setExpanded] = useState(false)
  if (tool.result === undefined && tool.resultPreview === undefined) {
    return null
  }

  const preview = tool.resultPreview ?? tool.result ?? ''
  const fullText = tool.result ?? preview
  const shown = expanded ? fullText : preview
  const totalLines = fullText.split('\n').length
  const resultClass = tool.isError
    ? 'mt-2 whitespace-pre-wrap text-pink-700'
    : 'mt-2 whitespace-pre-wrap text-stone-700'

  return (
    <div>
      <pre className={resultClass}>{`${tool.isError ? 'Error' : 'Result'}\n${shown}`}</pre>
      {tool.isTruncated && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className={tone === 'pink' ? 'mt-2 text-xs text-pink-700' : 'mt-2 text-xs text-emerald-700'}
        >
          {expanded ? 'Collapse' : `Show more (${totalLines} lines)`}
        </button>
      )}
    </div>
  )
}

function toolBorderClass(tool: ToolCall, tone: 'emerald' | 'pink') {
  if (tool.isError) return 'border-l-pink-500'
  if (tone === 'pink') return 'border-l-pink-500'
  if (tool.name === 'read') return 'border-l-sky-500'
  if (tool.name === 'bash') return 'border-l-emerald-500'
  if (tool.name === 'write' || tool.name === 'edit') return 'border-l-emerald-500'
  return 'border-l-emerald-500'
}

function formatParams(tool: ToolCall) {
  return tool.paramsPreview ?? JSON.stringify(tool.params)
}
