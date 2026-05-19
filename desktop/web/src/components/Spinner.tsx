import { useEffect, useState } from 'react'

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

interface SpinnerProps {
  label?: string
  className?: string
}

export function Spinner({ label = 'Thinking', className = '' }: SpinnerProps) {
  const [i, setI] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setI((x) => (x + 1) % FRAMES.length), 80)
    return () => clearInterval(timer)
  }, [])

  return (
    <span className={`font-mono text-sm text-amber-500/80 ${className}`}>
      {FRAMES[i]} {label}...
    </span>
  )
}
