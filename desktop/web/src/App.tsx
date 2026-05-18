import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { WindowA } from './windows/WindowA'
import { WindowB } from './windows/WindowB'

export default function App() {
  return (
    <main className="h-screen bg-zinc-950 text-zinc-100">
      <PanelGroup direction="horizontal">
        <Panel defaultSize={60} minSize={30}>
          <WindowA />
        </Panel>
        <PanelResizeHandle className="w-1 cursor-col-resize bg-zinc-300 hover:bg-zinc-400" />
        <Panel defaultSize={40} minSize={20}>
          <WindowB />
        </Panel>
      </PanelGroup>
    </main>
  )
}
