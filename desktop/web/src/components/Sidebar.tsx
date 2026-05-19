import { useAppStore } from '../state/store'

export function Sidebar() {
  const messagesA = useAppStore((state) => state.messagesA)
  const messagesB = useAppStore((state) => state.messagesB)
  const bTrigger = useAppStore((state) => state.bTrigger)

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-stone-200 bg-stone-100 text-sm text-stone-700">
      <div className="border-b border-stone-200 p-3">
        <button className="w-full rounded-xl bg-emerald-500 px-3 py-2 text-left text-sm font-medium text-white hover:bg-emerald-600">
          New conversation
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-3">
        <div className="space-y-1">
          <button className="w-full rounded-xl px-3 py-2 text-left hover:bg-white">
            Search
          </button>
          <button
            className="w-full rounded-xl px-3 py-2 text-left text-stone-400 hover:bg-white"
            title="Native folder picker is planned for the Tauri round."
          >
            Open folder
          </button>
        </div>

        <section className="mt-5">
          <h2 className="px-3 text-xs font-semibold uppercase text-stone-500">Project</h2>
          <div className="mt-2 rounded-xl bg-white p-2 shadow-sm ring-1 ring-stone-200">
            <div className="rounded-xl bg-stone-50 px-3 py-2 font-medium text-stone-900">
              OhMyCode
            </div>
            <div className="mt-2 space-y-1 text-xs text-stone-500">
              <div className="rounded-xl px-3 py-2 hover:bg-stone-50">
                Current session
              </div>
              <div className="rounded-xl px-3 py-2 hover:bg-stone-50">
                Prototype review
              </div>
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
