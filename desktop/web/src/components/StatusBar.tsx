import type { ConnectionStatus } from '../state/store'
import { useAppStore } from '../state/store'

const statusText: Record<ConnectionStatus, string> = {
  connecting: 'connecting',
  open: 'open',
  closed: 'closed',
  error: 'error',
}

const statusClass: Record<ConnectionStatus, string> = {
  connecting: 'text-stone-500',
  open: 'text-emerald-600',
  closed: 'text-pink-600',
  error: 'text-pink-600',
}

interface StatusBarProps {
  onProfile(): void
  onReconnect(): void
}

export function StatusBar({ onProfile, onReconnect }: StatusBarProps) {
  const status = useAppStore((state) => state.status)
  const runtime = useAppStore((state) => state.runtime)

  return (
    <header className="flex h-8 shrink-0 items-center gap-4 border-b border-stone-200 bg-white px-4 font-mono text-xs text-stone-500">
      <span className="font-semibold text-stone-900">OhMyCode</span>
      <span className="max-w-[28vw] truncate">{runtime?.cwd ?? 'cwd'}</span>
      <span className="truncate">A: {runtime?.aModel ?? '-'}</span>
      <span className="truncate">B: {runtime?.bModel ?? '-'}</span>
      <span className={statusClass[status]}>{statusText[status]}</span>
      {status !== 'open' && (
        <button className="text-emerald-700 underline" onClick={onReconnect}>
          reconnect
        </button>
      )}
      <button
        className="ml-auto rounded-full px-2 py-0.5 text-stone-600 hover:bg-stone-100 hover:text-emerald-700"
        onClick={onProfile}
      >
        profile
      </button>
    </header>
  )
}
