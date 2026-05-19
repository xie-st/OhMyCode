import { FormEvent, KeyboardEvent, useRef, useState } from 'react'
import { useAppStore } from '../state/store'

interface InputBarProps {
  sendMessage(text: string, target: 'A' | 'B'): void
  sendUserTyping(typing: boolean): void
}

export function InputBar({ sendMessage, sendUserTyping }: InputBarProps) {
  const [draft, setDraft] = useState('')
  const inputTarget = useAppStore((state) => state.inputTarget)
  const setInputTarget = useAppStore((state) => state.setInputTarget)
  const status = useAppStore((state) => state.status)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (!draft.trim()) {
      return
    }
    sendMessage(draft, inputTarget)
    setDraft('')
    sendUserTyping(false)
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const resize = () => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="shrink-0 border-t border-stone-200 bg-stone-50 px-4 pb-4 pt-2">
      <div className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
        <div className="mb-2 flex items-center gap-2">
          <TargetButton
            active={inputTarget === 'A'}
            label="@A Main"
            activeClass="bg-emerald-500 text-white"
            onClick={() => setInputTarget('A')}
          />
          <TargetButton
            active={inputTarget === 'B'}
            label="@B Coach"
            activeClass="bg-pink-500 text-white"
            onClick={() => setInputTarget('B')}
          />
          <button
            type="button"
            className="ml-auto flex h-7 w-7 items-center justify-center rounded-full bg-stone-100 font-mono text-lg text-stone-500 hover:bg-stone-200"
            title="File attachments are planned for a later round."
          >
            +
          </button>
        </div>

        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value)
            resize()
            sendUserTyping(event.target.value.length > 0)
          }}
          onBlur={() => sendUserTyping(false)}
          onFocus={() => draft && sendUserTyping(true)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask OhMyCode... Enter sends, Shift+Enter adds a line, Esc cancels."
          className="max-h-44 min-h-12 w-full resize-none bg-transparent font-mono text-sm leading-6 text-stone-900 outline-none placeholder:text-stone-400"
        />

        <div className="mt-2 flex items-center justify-between font-mono text-xs text-stone-400">
          <span>Esc cancel</span>
          <button
            type="submit"
            disabled={status !== 'open' || !draft.trim()}
            className="rounded-full bg-emerald-500 px-3 py-1 text-white disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-400"
          >
            Send
          </button>
        </div>
      </div>
    </form>
  )
}

function TargetButton({
  active,
  label,
  activeClass,
  onClick,
}: {
  active: boolean
  label: string
  activeClass: string
  onClick(): void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium ${
        active ? activeClass : 'bg-stone-100 text-stone-500 hover:bg-stone-200'
      }`}
    >
      {label}
    </button>
  )
}
