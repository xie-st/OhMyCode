import { useEffect } from 'react'
import type { PermissionAnswer, PermissionRequest } from '../state/store'

interface Props {
  request: PermissionRequest
  onResponse(answer: PermissionAnswer): void
}

export function PermissionPanel({ request, onResponse }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onResponse('n')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onResponse])

  const preview = request.paramsPreview ?? JSON.stringify(request.params).slice(0, 100)

  return (
    <div className="mx-4 mb-2 rounded-xl border border-pink-200 bg-pink-50 p-3 shadow-sm">
      <div className="flex min-w-0 items-center gap-3 font-mono text-xs">
        <span className="text-pink-700">!</span>
        <span className="font-semibold text-stone-900">Window {request.window} request</span>
        <span className="text-stone-700">{request.tool_name}</span>
        <span className="min-w-0 flex-1 truncate text-stone-500">{preview}</span>
        <button
          onClick={() => onResponse('n')}
          className="rounded-full bg-stone-200 px-3 py-1 text-stone-700 hover:bg-stone-300"
        >
          Deny (Esc)
        </button>
        <button
          onClick={() => onResponse('y')}
          className="rounded-full bg-emerald-500 px-3 py-1 text-white hover:bg-emerald-600"
        >
          Allow once
        </button>
        <button
          onClick={() => onResponse('a')}
          className="rounded-full border border-emerald-500 px-3 py-1 text-emerald-700 hover:bg-emerald-50"
        >
          Always allow
        </button>
      </div>
    </div>
  )
}
