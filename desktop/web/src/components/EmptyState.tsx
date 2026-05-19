interface EmptyStateProps {
  title: string
  accent: 'emerald' | 'pink'
}

export function EmptyState({ title, accent }: EmptyStateProps) {
  const color = accent === 'emerald' ? 'text-emerald-600' : 'text-pink-600'

  return (
    <div className="flex h-full items-center justify-center px-6 text-center">
      <div>
        <div className={`font-mono text-xs font-semibold uppercase ${color}`}>{title}</div>
        <p className="mt-3 text-lg font-semibold text-stone-900">
          What should OhMyCode do?
        </p>
        <p className="mt-2 max-w-sm text-sm text-stone-500">
          Start with the shared input below, or switch the target to ask Window B.
        </p>
      </div>
    </div>
  )
}
