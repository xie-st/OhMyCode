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

export interface ProfileEvidence {
  id: string
  ts?: string
  context?: string
  is_gap?: boolean
}

export interface Profile {
  cwd: string
  skills: Record<string, { level?: number; evidence_count?: number }>
  concepts: Record<
    string,
    {
      level?: number
      evidence_count?: number
      last_seen?: string
      evidence?: ProfileEvidence[]
    }
  >
  knowledge_gaps: Array<{ id?: string; text?: string; ts?: string }>
  recent_messages: string[]
  interaction_style: Record<string, unknown>
}

interface StreamEvent {
  type: string
  data: Record<string, unknown>
  window?: 'A' | 'B'
}

interface AppState {
  status: ConnectionStatus
  messagesA: Message[]
  messagesB: Message[]
  bTrigger: string
  profile: Profile | null
  userTyping: boolean
  setStatus(status: ConnectionStatus): void
  setUserTyping(typing: boolean): void
  fetchProfile(): Promise<void>
  deleteEvidence(evidenceId: string): Promise<void>
  clearProfile(): Promise<void>
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

const ingestMessageEvent = (messages: Message[], event: StreamEvent) => {
  if (event.type === 'TextChunk') {
    const nextMessages = ensureAssistant(messages)
    const last = nextMessages[nextMessages.length - 1]
    return [
      ...nextMessages.slice(0, -1),
      { ...last, text: `${last.text}${String(event.data.text ?? '')}` },
    ]
  }

  if (event.type === 'ToolCallStart') {
    const nextMessages = ensureAssistant(messages)
    const last = nextMessages[nextMessages.length - 1]
    const toolCalls = [
      ...(last.toolCalls ?? []),
      {
        id: String(event.data.tool_use_id ?? ''),
        name: String(event.data.tool_name ?? ''),
        params: event.data.params ?? {},
      },
    ]
    return [...nextMessages.slice(0, -1), { ...last, toolCalls }]
  }

  if (event.type === 'ToolCallResult') {
    const nextMessages = ensureAssistant(messages)
    const last = nextMessages[nextMessages.length - 1]
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
    return [...nextMessages.slice(0, -1), { ...last, toolCalls }]
  }

  return messages
}

export const useAppStore = create<AppState>((set) => ({
  status: 'connecting',
  messagesA: [],
  messagesB: [],
  bTrigger: '',
  profile: null,
  userTyping: false,

  setStatus: (status) => set({ status }),

  setUserTyping: (userTyping) => set({ userTyping }),

  fetchProfile: async () => {
    const response = await fetch('/api/profile')
    if (!response.ok) {
      set({ profile: null })
      return
    }
    set({ profile: (await response.json()) as Profile })
  },

  deleteEvidence: async (evidenceId) => {
    const response = await fetch(`/api/profile/evidence/${evidenceId}`, {
      method: 'DELETE',
    })
    if (response.ok) {
      await useAppStore.getState().fetchProfile()
    }
  },

  clearProfile: async () => {
    const response = await fetch('/api/profile', { method: 'DELETE' })
    if (response.ok) {
      await useAppStore.getState().fetchProfile()
    }
  },

  appendUserMessage: (text) =>
    set((state) => ({
      messagesA: [...state.messagesA, { id: makeId(), role: 'user', text }],
    })),

  ingestEvent: (event) =>
    set((state) => {
      if (event.type === 'error') {
        return { status: 'error' }
      }

      if (event.window === 'B') {
        if (event.type === 'TurnComplete') {
          return { bTrigger: '' }
        }
        return {
          messagesB: ingestMessageEvent(state.messagesB, event),
          bTrigger: event.type === 'TextChunk' ? '讲解中' : state.bTrigger,
        }
      }

      if (event.type === 'TurnComplete') {
        return state
      }

      return { messagesA: ingestMessageEvent(state.messagesA, event) }
    }),
}))
