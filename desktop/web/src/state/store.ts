import { create } from 'zustand'

export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error'
export type PermissionAnswer = 'y' | 'a' | 'n'

export interface ToolCall {
  id: string
  name: string
  params: unknown
  paramsPreview?: string      // server-side truncated (see render_rules.py)
  result?: string             // full text, kept for the expand toggle
  resultPreview?: string      // server-side truncated
  isTruncated?: boolean       // whether resultPreview is shorter than result
  isError?: boolean
}

export type AssistantSegment =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; tool: ToolCall }

export interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  segments?: AssistantSegment[]
  error?: string
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  project_slug: string
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
  paramsPreview?: string
  window: 'A' | 'B'
}

export interface RuntimeInfo {
  cwd: string
  aModel: string
  bModel: string
  provider: string
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
  sessions: Session[]
  currentSessionId: string | null
  isSwitchingSession: boolean
  switchingSessionId: string | null
  inputTarget: 'A' | 'B'
  runtime: RuntimeInfo | null
  isATurnActive: boolean
  isBTurnActive: boolean
  bTrigger: string
  bTriggerClearAt: number | null
  profile: Profile | null
  userTyping: boolean
  pendingPermission: PermissionRequest | null
  setStatus(status: ConnectionStatus): void
  setInputTarget(target: 'A' | 'B'): void
  setATurnActive(active: boolean): void
  setBTurnActive(active: boolean): void
  setUserTyping(typing: boolean): void
  clearPendingPermission(): void
  setSwitchingSession(sessionId: string | null): void
  setSessionSwitcher(switcher: ((sessionId: string) => void) | null): void
  fetchSessions(): Promise<void>
  switchSession(sessionId: string): void
  createSession(): Promise<void>
  deleteSession(sessionId: string): Promise<void>
  fetchProfile(): Promise<void>
  deleteEvidence(evidenceId: string): Promise<void>
  clearProfile(): Promise<void>
  ingestEvent(event: StreamEvent): void
  appendUserMessage(text: string, target?: 'A' | 'B'): void
}

const makeId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
let bTriggerTimer: ReturnType<typeof setTimeout> | null = null
let sessionSwitcher: ((sessionId: string) => void) | null = null

const ensureAssistant = (messages: Message[]): Message[] => {
  const last = messages[messages.length - 1]
  if (last?.role === 'assistant') {
    return messages
  }
  return [...messages, { id: makeId(), role: 'assistant', text: '', segments: [] }]
}

const appendTextSegment = (message: Message, text: string): Message => {
  const segments = message.segments ?? []
  const lastSegment = segments[segments.length - 1]

  if (lastSegment?.kind === 'text') {
    return {
      ...message,
      text: `${message.text}${text}`,
      segments: [
        ...segments.slice(0, -1),
        { kind: 'text', text: `${lastSegment.text}${text}` },
      ],
    }
  }

  return {
    ...message,
    text: `${message.text}${text}`,
    segments: [...segments, { kind: 'text', text }],
  }
}

const updateToolSegment = (
  message: Message,
  toolId: string,
  patch: Partial<ToolCall>,
): Message => ({
  ...message,
  segments: (message.segments ?? []).map((segment) =>
    segment.kind === 'tool' && segment.tool.id === toolId
      ? { kind: 'tool', tool: { ...segment.tool, ...patch } }
      : segment,
  ),
})

const ingestMessageEvent = (messages: Message[], event: StreamEvent): Message[] => {
  if (event.type === 'TextChunk') {
    const nextMessages = ensureAssistant(messages)
    const last = nextMessages[nextMessages.length - 1]
    return [...nextMessages.slice(0, -1), appendTextSegment(last, String(event.data.text ?? ''))]
  }

  if (event.type === 'ToolCallStart') {
    const nextMessages = ensureAssistant(messages)
    const last = nextMessages[nextMessages.length - 1]
    const segments = [
      ...(last.segments ?? []),
      {
        kind: 'tool' as const,
        tool: {
          id: String(event.data.tool_use_id ?? ''),
          name: String(event.data.tool_name ?? ''),
          params: event.data.params ?? {},
          paramsPreview:
            typeof event.data.params_preview === 'string'
              ? event.data.params_preview
              : undefined,
        },
      },
    ]
    return [...nextMessages.slice(0, -1), { ...last, segments }]
  }

  if (event.type === 'ToolCallResult') {
    const nextMessages = ensureAssistant(messages)
    const last = nextMessages[nextMessages.length - 1]
    const toolId = String(event.data.tool_use_id ?? '')
    return [
      ...nextMessages.slice(0, -1),
      updateToolSegment(last, toolId, {
        result: String(event.data.result ?? ''),
        resultPreview:
          typeof event.data.result_preview === 'string'
            ? event.data.result_preview
            : undefined,
        isTruncated: Boolean(event.data.is_truncated),
        isError: Boolean(event.data.is_error),
      }),
    ]
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
  sessions: [],
  currentSessionId: null,
  isSwitchingSession: false,
  switchingSessionId: null,
  inputTarget: 'A',
  runtime: null,
  isATurnActive: false,
  isBTurnActive: false,
  bTrigger: '',
  bTriggerClearAt: null,
  profile: null,
  userTyping: false,
  pendingPermission: null,

  setStatus: (status) => set({ status }),

  setInputTarget: (inputTarget) => set({ inputTarget }),

  setATurnActive: (isATurnActive) => set({ isATurnActive }),

  setBTurnActive: (isBTurnActive) => set({ isBTurnActive }),

  setUserTyping: (userTyping) => set({ userTyping }),

  clearPendingPermission: () => set({ pendingPermission: null }),

  setSwitchingSession: (sessionId) =>
    set({
      isSwitchingSession: sessionId !== null,
      switchingSessionId: sessionId,
    }),

  setSessionSwitcher: (switcher) => {
    sessionSwitcher = switcher
  },

  fetchSessions: async () => {
    const response = await fetch('/api/sessions')
    if (!response.ok) {
      set({ sessions: [] })
      return
    }
    set({ sessions: (await response.json()) as Session[] })
  },

  switchSession: (sessionId) => {
    sessionSwitcher?.(sessionId)
  },

  createSession: async () => {
    const response = await fetch('/api/sessions', { method: 'POST' })
    if (!response.ok) {
      return
    }
    const session = (await response.json()) as Session
    set((state) => ({ sessions: [session, ...state.sessions] }))
    sessionSwitcher?.(session.id)
  },

  deleteSession: async (sessionId) => {
    const response = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
    if (response.ok) {
      set((state) => ({
        sessions: state.sessions.filter((session) => session.id !== sessionId),
      }))
    }
  },

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

  appendUserMessage: (text, target = 'A') =>
    set((state) => ({
      messagesA:
        target === 'A'
          ? [...state.messagesA, { id: makeId(), role: 'user', text }]
          : state.messagesA,
      messagesB:
        target === 'B'
          ? [...state.messagesB, { id: makeId(), role: 'user', text }]
          : state.messagesB,
      isATurnActive: target === 'A' ? true : state.isATurnActive,
      isBTurnActive: target === 'B' ? true : state.isBTurnActive,
    })),

  ingestEvent: (event) =>
    set((state) => {
      const eventWindow = getEventWindow(event)

      if (event.type === 'runtime_info') {
        return {
          runtime: {
            cwd: String(event.data.cwd ?? ''),
            aModel: String(event.data.a_model ?? ''),
            bModel: String(event.data.b_model ?? ''),
            provider: String(event.data.provider ?? ''),
          },
        }
      }

      if (event.type === 'current_session') {
        const session = event.data as unknown as Session
        return {
          currentSessionId: String(event.data.id ?? ''),
          sessions: [
            session,
            ...state.sessions.filter((item) => item.id !== event.data.id),
          ],
        }
      }

      if (event.type === 'history_loaded') {
        return {
          messagesA: (event.data.messagesA ?? []) as unknown as Message[],
          messagesB: (event.data.messagesB ?? []) as unknown as Message[],
          isSwitchingSession: false,
          switchingSessionId: null,
          isATurnActive: false,
          isBTurnActive: false,
          bTrigger: '',
          bTriggerClearAt: null,
        }
      }

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
            isBTurnActive: false,
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
            paramsPreview:
              typeof event.data.params_preview === 'string'
                ? event.data.params_preview
                : undefined,
            window: event.data.window === 'B' ? 'B' : 'A',
          },
        }
      }

      if (eventWindow === 'B') {
        if (event.type === 'TurnComplete') {
          return { bTriggerClearAt: scheduleBTriggerClear(), isBTurnActive: false }
        }
        return {
          messagesB: ingestMessageEvent(state.messagesB, event),
          isBTurnActive: true,
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
