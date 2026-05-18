import { useEffect, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { PermissionDialog } from './components/PermissionDialog'
import { ProfileDrawer } from './components/ProfileDrawer'
import { useWebSocket } from './hooks/useWebSocket'
import { useAppStore } from './state/store'
import { WindowA } from './windows/WindowA'
import { WindowB } from './windows/WindowB'

export default function App() {
  const [showProfile, setShowProfile] = useState(false)
  const pendingPermission = useAppStore((state) => state.pendingPermission)
  const clearPendingPermission = useAppStore((state) => state.clearPendingPermission)
  const { sendMessage, cancel, sendUserTyping, sendPermissionResponse } = useWebSocket()

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return
      }
      if (pendingPermission) {
        return
      }
      cancel()
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cancel, pendingPermission])

  return (
    <main className="h-screen bg-zinc-950 text-zinc-100">
      <button
        className="fixed right-4 top-3 z-30 rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
        onClick={() => setShowProfile(true)}
      >
        我的画像
      </button>
      <PanelGroup direction="horizontal">
        <Panel defaultSize={60} minSize={30}>
          <WindowA
            sendMessage={sendMessage}
            sendUserTyping={sendUserTyping}
          />
        </Panel>
        <PanelResizeHandle className="w-1 cursor-col-resize bg-zinc-300 hover:bg-zinc-400" />
        <Panel defaultSize={40} minSize={20}>
          <WindowB />
        </Panel>
      </PanelGroup>
      <ProfileDrawer open={showProfile} onClose={() => setShowProfile(false)} />
      {pendingPermission && (
        <PermissionDialog
          request={pendingPermission}
          onResponse={(answer) => {
            sendPermissionResponse(pendingPermission.request_id, answer)
            clearPendingPermission()
          }}
        />
      )}
    </main>
  )
}
