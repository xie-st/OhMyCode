import { useEffect, useState } from 'react'
import { useAppStore } from '../state/store'

export function Sidebar() {
  const messagesA = useAppStore((state) => state.messagesA)
  const messagesB = useAppStore((state) => state.messagesB)
  const bTrigger = useAppStore((state) => state.bTrigger)
  const sessions = useAppStore((state) => state.sessions)
  const currentSessionId = useAppStore((state) => state.currentSessionId)
  const fetchSessions = useAppStore((state) => state.fetchSessions)
  const createSession = useAppStore((state) => state.createSession)
  const switchSession = useAppStore((state) => state.switchSession)
  const [folderHint, setFolderHint] = useState(false)

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-stone-200 bg-stone-100 text-sm text-stone-700">
      <div className="border-b border-stone-200 p-3">
        <button
          onClick={() => createSession()}
          title="Creates a session in the current project."
          className="w-full rounded-xl bg-emerald-500 px-3 py-2 text-left text-sm font-medium text-white hover:bg-emerald-600"
        >
          New conversation (in current project)
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-3">
        <div className="space-y-1">
          <button className="w-full rounded-xl px-3 py-2 text-left hover:bg-white">
            Search
          </button>
          <button
            className="w-full rounded-xl px-3 py-2 text-left text-stone-400 hover:bg-white"
            onClick={() => setFolderHint(true)}
            title="Native folder picker is planned for the Tauri round. New conversations stay in the current project."
          >
            Open folder
          </button>
          {folderHint && (
            <div className="px-3 py-1 text-xs text-stone-500">
              Folder switching lands in the Tauri round. New conversations are sessions inside the current project.
            </div>
          )}
        </div>

        <section className="mt-5">
          <h2 className="px-3 text-xs font-semibold uppercase text-stone-500">Project</h2>
          <div className="mt-2 rounded-xl bg-white p-2 shadow-sm ring-1 ring-stone-200">
            <div className="rounded-xl bg-stone-50 px-3 py-2 font-medium text-stone-900">
              OhMyCode
            </div>
            <div className="mt-2 space-y-1 text-xs">
              {sessions.map((session) => {
                const active = session.id === currentSessionId
                return (
                  <button
                    key={session.id}
                    onClick={() => switchSession(session.id)}
                    className={[
                      'w-full rounded-xl px-3 py-2 text-left hover:bg-stone-50',
                      active ? 'bg-emerald-50 text-emerald-700' : 'text-stone-500',
                    ].join(' ')}
                  >
                    <span className="block truncate font-medium">{session.title}</span>
                    <span className="block text-[11px] text-stone-400">
                      {formatRelativeTime(session.updated_at)}
                    </span>
                  </button>
                )
              })}
              {sessions.length === 0 && (
                <div className="rounded-xl px-3 py-2 text-stone-400">
                  No sessions yet
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="mt-5">
          <h2 className="px-3 text-xs font-semibold uppercase text-stone-500">Activity</h2>
          <div className="mt-2 space-y-2 px-3 font-mono text-xs text-stone-500">
            <div>A messages: {messagesA.length}</div>
            <div>B messages: {messagesB.length}</div>
            {bTrigger && <div className="text-pink-600">B: {bTrigger}</div>}
          </div>
        </section>
      </nav>

      <div className="border-t border-stone-200 p-3">
        <button className="w-full rounded-xl px-3 py-2 text-left text-stone-600 hover:bg-white">
          Settings
        </button>
      </div>
    </aside>
  )
}

function formatRelativeTime(value: string) {
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) {
    return ''
  }
  const diffMs = Date.now() - timestamp
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour

  if (diffMs < hour) return `${Math.max(1, Math.floor(diffMs / minute))} min ago`
  if (diffMs < day) return `${Math.floor(diffMs / hour)} h ago`
  return `${Math.floor(diffMs / day)} d ago`
}
