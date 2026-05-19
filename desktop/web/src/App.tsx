import { useEffect, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { InputBar } from './components/InputBar'
import { PermissionPanel } from './components/PermissionPanel'
import { ProfileDrawer } from './components/ProfileDrawer'
import { Sidebar } from './components/Sidebar'
import { StatusBar } from './components/StatusBar'
import { useWebSocket } from './hooks/useWebSocket'
import { useAppStore } from './state/store'
import { WindowA } from './windows/WindowA'
import { WindowB } from './windows/WindowB'

export default function App() {
  const [showProfile, setShowProfile] = useState(false)
  const pendingPermission = useAppStore((state) => state.pendingPermission)
  const clearPendingPermission = useAppStore((state) => state.clearPendingPermission)
  const {
    sendMessage,
    cancel,
    sendUserTyping,
    sendPermissionResponse,
    reconnect,
  } = useWebSocket()

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
    <main className="flex h-screen flex-col bg-stone-50 text-stone-900">
      <StatusBar onProfile={() => setShowProfile(true)} onReconnect={reconnect} />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <section className="flex min-w-0 flex-1 flex-col">
          <PanelGroup direction="horizontal">
            <Panel defaultSize={60} minSize={30}>
              <WindowA />
            </Panel>
            <PanelResizeHandle className="w-1 cursor-col-resize bg-stone-200 hover:bg-stone-300" />
            <Panel defaultSize={40} minSize={20}>
              <WindowB />
            </Panel>
          </PanelGroup>
          {pendingPermission && (
            <PermissionPanel
              request={pendingPermission}
              onResponse={(answer) => {
                sendPermissionResponse(pendingPermission.request_id, answer)
                clearPendingPermission()
              }}
            />
          )}
          <InputBar sendMessage={sendMessage} sendUserTyping={sendUserTyping} />
        </section>
      </div>
      <ProfileDrawer open={showProfile} onClose={() => setShowProfile(false)} />
    </main>
  )
}
