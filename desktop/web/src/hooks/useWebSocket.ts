import { useCallback, useEffect, useRef } from 'react'
import { useAppStore, type PermissionAnswer } from '../state/store'

const WS_URL = 'ws://localhost:5173/ws'
const AUTO_RETRY_DELAY_MS = 2000

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const mountedRef = useRef(false)
  const pendingSessionRef = useRef<string | null>(null)
  const autoRetryTriedRef = useRef(false)
  const autoRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmuteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const ingestEvent = useAppStore((state) => state.ingestEvent)
  const appendUserMessage = useAppStore((state) => state.appendUserMessage)
  const setStatus = useAppStore((state) => state.setStatus)
  const setUserTypingState = useAppStore((state) => state.setUserTyping)
  const setSwitchingSession = useAppStore((state) => state.setSwitchingSession)
  const setSessionSwitcher = useAppStore((state) => state.setSessionSwitcher)

  const connect = useCallback(() => {
    if (autoRetryTimerRef.current) {
      clearTimeout(autoRetryTimerRef.current)
      autoRetryTimerRef.current = null
    }
    if (socketRef.current && socketRef.current.readyState !== WebSocket.CLOSED) {
      socketRef.current.close()
    }
    setStatus('connecting')
    const url = pendingSessionRef.current
      ? `${WS_URL}?session=${encodeURIComponent(pendingSessionRef.current)}`
      : WS_URL
    const socket = new WebSocket(url)
    socketRef.current = socket

    socket.onopen = () => {
      autoRetryTriedRef.current = false
      setStatus('open')
    }
    socket.onerror = () => setStatus('error')
    socket.onclose = () => {
      setStatus('closed')
      if (!autoRetryTriedRef.current) {
        autoRetryTriedRef.current = true
        autoRetryTimerRef.current = setTimeout(() => {
          autoRetryTimerRef.current = null
          connect()
        }, AUTO_RETRY_DELAY_MS)
      }
    }
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data)
        ingestEvent(event)
        if (event.type === 'TurnComplete') {
          const target = event.window === 'B' ? 'B' : 'A'
          setTimeout(() => {
            const state = useAppStore.getState()
            const messages = target === 'B' ? state.messagesB : state.messagesA
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(
                JSON.stringify({
                  type: 'save_session',
                  data: { target, messages },
                }),
              )
              void useAppStore.getState().fetchSessions()
            }
          }, 0)
        }
      } catch {
        setStatus('error')
      }
    }
  }, [ingestEvent, setStatus])

  const reconnect = useCallback(() => {
    autoRetryTriedRef.current = false
    connect()
  }, [connect])

  const switchSession = useCallback(
    (sessionId: string) => {
      const socket = socketRef.current
      setSwitchingSession(sessionId)
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            type: 'switch_session',
            data: { session_id: sessionId },
          }),
        )
        return
      }
      pendingSessionRef.current = sessionId
      autoRetryTriedRef.current = true
      connect()
    },
    [connect, setSwitchingSession],
  )

  useEffect(() => {
    if (mountedRef.current) return
    mountedRef.current = true
    setSessionSwitcher(switchSession)
    connect()
    return () => {
      mountedRef.current = false
      autoRetryTriedRef.current = true
      setSessionSwitcher(null)
      if (unmuteTimerRef.current) clearTimeout(unmuteTimerRef.current)
      if (autoRetryTimerRef.current) clearTimeout(autoRetryTimerRef.current)
      const socket = socketRef.current
      socketRef.current = null
      if (socket) socket.close()
    }
  }, [])

  const sendMessage = useCallback(
    (text: string, target: 'A' | 'B' = 'A') => {
      const trimmed = text.trim()
      const socket = socketRef.current
      if (!trimmed || socket?.readyState !== WebSocket.OPEN) {
        return
      }
      appendUserMessage(trimmed, target)
      socket.send(JSON.stringify({ type: 'user_input', data: { text: trimmed, target } }))
    },
    [appendUserMessage],
  )

  const cancel = useCallback(() => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'cancel' }))
    }
  }, [])

  const sendPermissionResponse = useCallback((requestId: string, answer: PermissionAnswer) => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: 'permission_response',
          data: { request_id: requestId, answer },
        }),
      )
    }
  }, [])

  const sendUserTyping = useCallback(
    (typing: boolean) => {
      if (unmuteTimerRef.current) {
        clearTimeout(unmuteTimerRef.current)
        unmuteTimerRef.current = null
      }

      const send = (nextTyping: boolean) => {
        setUserTypingState(nextTyping)
        const socket = socketRef.current
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'user_typing', data: { typing: nextTyping } }))
        }
      }

      if (typing) {
        send(true)
        return
      }

      unmuteTimerRef.current = setTimeout(() => send(false), 300)
    },
    [setUserTypingState],
  )

  return {
    sendMessage,
    cancel,
    sendUserTyping,
    sendPermissionResponse,
    reconnect,
    switchSession,
  }
}
