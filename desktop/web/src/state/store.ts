import { create } from 'zustand'

export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error'
export type PermissionAnswer = 'y' | 'a' | 'n'

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
  error?: string
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

export interface PermissionRequest {
  request_id: string
  tool_name: string
  params: Record<string, unknown>
  window: 'A' | 'B'
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
  isATurnActive: boolean
  bTrigger: string
  bTriggerClearAt: number | null
  profile: Profile | null
  userTyping: boolean
  pendingPermission: PermissionRequest | null
  setStatus(status: ConnectionStatus): void
  setATurnActive(active: boolean): void
  setUserTyping(typing: boolean): void
  clearPendingPermission(): void
  fetchProfile(): Promise<void>
  deleteEvidence(evidenceId: string): Promise<void>
  clearProfile(): Promise<void>
  ingestEvent(event: StreamEvent): void
  appendUserMessage(text: string): void
}

const makeId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
let bTriggerTimer: ReturnType<typeof setTimeout> | null = null

const ensureAssistant = (messages: Message[]): Message[] => {
  const last = messages[messages.length - 1]
  if (last?.role === 'assistant') {
    return messages
  }
  return [...messages, { id: makeId(), role: 'assistant', text: '', toolCalls: [] }]
}

const ingestMessageEvent = (messages: Message[], event: StreamEvent): Message[] => {
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

const getEventWindow = (event: StreamEvent) => event.window ?? event.data.window

const scheduleBTriggerClear = () => {
  if (bTriggerTimer) {
    clearTimeout(bTriggerTimer)
  }

  const clearAt = Date.now() + 5000
  bTriggerTimer = setTimeout(() => {
    useAppStore.setState((state) =>
      state.bTriggerClearAt === clearAt ? { bTrigger: '', bTriggerClearAt: null } : {},
    )
    bTriggerTimer = null
  }, 5000)

  return clearAt
}

export const useAppStore = create<AppState>((set) => ({
  status: 'connecting',
  messagesA: [],
  messagesB: [],
  isATurnActive: false,
  bTrigger: '',
  bTriggerClearAt: null,
  profile: null,
  userTyping: false,
  pendingPermission: null,

  setStatus: (status) => set({ status }),

  setATurnActive: (isATurnActive) => set({ isATurnActive }),

  setUserTyping: (userTyping) => set({ userTyping }),

  clearPendingPermission: () => set({ pendingPermission: null }),

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
      isATurnActive: true,
    })),

  ingestEvent: (event) =>
    set((state) => {
      const eventWindow = getEventWindow(event)

      if (event.type === 'error') {
        if (eventWindow === 'B') {
          return {
            messagesB: [
              ...state.messagesB,
              {
                id: makeId(),
                role: 'assistant',
                text: 'B window could not finish the explanation.',
                error: String(event.data.message ?? 'unknown error'),
              },
            ],
            bTrigger: '',
            bTriggerClearAt: null,
          }
        }

        return { status: 'error', isATurnActive: false }
      }

      if (event.type === 'permission_request') {
        return {
          pendingPermission: {
            request_id: String(event.data.request_id ?? ''),
            tool_name: String(event.data.tool_name ?? ''),
            params: (event.data.params ?? {}) as Record<string, unknown>,
            window: event.data.window === 'B' ? 'B' : 'A',
          },
        }
      }

      if (eventWindow === 'B') {
        if (event.type === 'TurnComplete') {
          return { bTriggerClearAt: scheduleBTriggerClear() }
        }
        return {
          messagesB: ingestMessageEvent(state.messagesB, event),
          bTrigger: event.type === 'TextChunk' ? 'Explaining' : state.bTrigger,
          bTriggerClearAt: null,
        }
      }

      if (event.type === 'TurnComplete') {
        return { isATurnActive: false }
      }

      return { messagesA: ingestMessageEvent(state.messagesA, event) }
    }),
}))
