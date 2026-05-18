import { create } from 'zustand'

export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error'

export interface ToolCall {
  id: string
  name: string
  params: unknown
  result?: string
  isError?: boolean
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  toolCalls?: ToolCall[]
}

interface StreamEvent {
  type: string
  data: Record<string, unknown>
}

interface AppState {
  status: ConnectionStatus
  messages: Message[]
  setStatus(status: ConnectionStatus): void
  ingestEvent(event: StreamEvent): void
  appendUserMessage(text: string): void
}

const makeId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

const ensureAssistant = (messages: Message[]) => {
  const last = messages[messages.length - 1]
  if (last?.role === 'assistant') {
    return messages
  }
  return [...messages, { id: makeId(), role: 'assistant', text: '', toolCalls: [] }]
}

export const useAppStore = create<AppState>((set) => ({
  status: 'connecting',
  messages: [],

  setStatus: (status) => set({ status }),

  appendUserMessage: (text) =>
    set((state) => ({
      messages: [...state.messages, { id: makeId(), role: 'user', text }],
    })),

  ingestEvent: (event) =>
    set((state) => {
      if (event.type === 'TextChunk') {
        const messages = ensureAssistant(state.messages)
        const last = messages[messages.length - 1]
        return {
          messages: [
            ...messages.slice(0, -1),
            { ...last, text: `${last.text}${String(event.data.text ?? '')}` },
          ],
        }
      }

      if (event.type === 'ToolCallStart') {
        const messages = ensureAssistant(state.messages)
        const last = messages[messages.length - 1]
        const toolCalls = [
          ...(last.toolCalls ?? []),
          {
            id: String(event.data.tool_use_id ?? ''),
            name: String(event.data.tool_name ?? ''),
            params: event.data.params ?? {},
          },
        ]
        return { messages: [...messages.slice(0, -1), { ...last, toolCalls }] }
      }

      if (event.type === 'ToolCallResult') {
        const messages = ensureAssistant(state.messages)
        const last = messages[messages.length - 1]
        const toolId = String(event.data.tool_use_id ?? '')
        const toolCalls = (last.toolCalls ?? []).map((call) =>
          call.id === toolId
            ? {
                ...call,
                result: String(event.data.result ?? ''),
                isError: Boolean(event.data.is_error),
              }
            : call,
        )
        return { messages: [...messages.slice(0, -1), { ...last, toolCalls }] }
      }

      if (event.type === 'TurnComplete') {
        return state
      }

      if (event.type === 'error') {
        return { status: 'error' }
      }

      return state
    }),
}))
