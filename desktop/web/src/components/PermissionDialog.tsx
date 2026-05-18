import { useEffect } from 'react'
import type { PermissionAnswer, PermissionRequest } from '../state/store'

interface Props {
  request: PermissionRequest
  onResponse(answer: PermissionAnswer): void
}

export function PermissionDialog({ request, onResponse }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onResponse('n')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onResponse])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <section className="w-full max-w-lg rounded border border-zinc-700 bg-zinc-950 p-5 text-zinc-100 shadow-2xl">
        <header className="mb-4">
          <h2 className="text-sm font-semibold">Window {request.window} requests permission</h2>
          <p className="mt-1 text-xs text-zinc-400">Review the tool call before it runs.</p>
        </header>

        <div className="space-y-3">
          <div>
            <div className="mb-1 text-xs font-medium uppercase tracking-normal text-zinc-500">Tool</div>
            <div className="rounded border border-zinc-800 bg-zinc-900 px-3 py-2 font-mono text-sm text-cyan-200">
              {request.tool_name}
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-medium uppercase tracking-normal text-zinc-500">
              Parameters
            </div>
            <pre className="max-h-56 overflow-auto rounded border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300">
              {JSON.stringify(request.params, null, 2)}
            </pre>
          </div>
        </div>

        <footer className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            className="rounded border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
            onClick={() => onResponse('n')}
          >
            Deny
          </button>
          <button
            className="rounded bg-cyan-600 px-3 py-2 text-sm font-medium text-white hover:bg-cyan-500"
            onClick={() => onResponse('y')}
          >
            Allow once
          </button>
          <button
            className="rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
            onClick={() => onResponse('a')}
          >
            Always allow
          </button>
        </footer>
      </section>
    </div>
  )
}
