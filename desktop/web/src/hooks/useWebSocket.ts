import { useCallback, useEffect, useRef } from 'react'
import { useAppStore, type PermissionAnswer } from '../state/store'

const WS_URL = 'ws://localhost:5173/ws'
const AUTO_RETRY_DELAY_MS = 2000

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const autoRetryTriedRef = useRef(false)
  const autoRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmuteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const ingestEvent = useAppStore((state) => state.ingestEvent)
  const appendUserMessage = useAppStore((state) => state.appendUserMessage)
  const setStatus = useAppStore((state) => state.setStatus)
  const setUserTypingState = useAppStore((state) => state.setUserTyping)

  const connect = useCallback(() => {
    if (autoRetryTimerRef.current) {
      clearTimeout(autoRetryTimerRef.current)
      autoRetryTimerRef.current = null
    }
    if (socketRef.current && socketRef.current.readyState !== WebSocket.CLOSED) {
      socketRef.current.close()
    }
    setStatus('connecting')
    const socket = new WebSocket(WS_URL)
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
        ingestEvent(JSON.parse(message.data))
      } catch {
        setStatus('error')
      }
    }
  }, [ingestEvent, setStatus])

  const reconnect = useCallback(() => {
    autoRetryTriedRef.current = false
    connect()
  }, [connect])

  useEffect(() => {
    connect()
    return () => {
      if (unmuteTimerRef.current) clearTimeout(unmuteTimerRef.current)
      if (autoRetryTimerRef.current) clearTimeout(autoRetryTimerRef.current)
      const socket = socketRef.current
      socketRef.current = null
      if (socket) socket.close()
    }
  }, [connect])

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

  return { sendMessage, cancel, sendUserTyping, sendPermissionResponse, reconnect }
}
