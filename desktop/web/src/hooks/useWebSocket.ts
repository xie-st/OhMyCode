import { useCallback, useEffect, useRef } from 'react'
import { useAppStore } from '../state/store'

const WS_URL = 'ws://localhost:5173/ws'

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const unmuteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const ingestEvent = useAppStore((state) => state.ingestEvent)
  const appendUserMessage = useAppStore((state) => state.appendUserMessage)
  const setStatus = useAppStore((state) => state.setStatus)
  const setUserTypingState = useAppStore((state) => state.setUserTyping)

  useEffect(() => {
    setStatus('connecting')
    const socket = new WebSocket(WS_URL)
    socketRef.current = socket

    socket.onopen = () => setStatus('open')
    socket.onclose = () => setStatus('closed')
    socket.onerror = () => setStatus('error')
    socket.onmessage = (message) => {
      try {
        ingestEvent(JSON.parse(message.data))
      } catch {
        setStatus('error')
      }
    }

    return () => {
      if (unmuteTimerRef.current) {
        clearTimeout(unmuteTimerRef.current)
      }
      socket.close()
      socketRef.current = null
    }
  }, [ingestEvent, setStatus])

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      const socket = socketRef.current
      if (!trimmed || socket?.readyState !== WebSocket.OPEN) {
        return
      }
      appendUserMessage(trimmed)
      socket.send(JSON.stringify({ type: 'user_input', data: { text: trimmed } }))
    },
    [appendUserMessage],
  )

  const cancel = useCallback(() => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'cancel' }))
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

  return { sendMessage, cancel, sendUserTyping }
}
