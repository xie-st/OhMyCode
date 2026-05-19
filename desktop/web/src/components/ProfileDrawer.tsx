import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { useAppStore, type ProfileEvidence } from '../state/store'

interface ProfileDrawerProps {
  open: boolean
  onClose(): void
}

export function ProfileDrawer({ open, onClose }: ProfileDrawerProps) {
  const profile = useAppStore((state) => state.profile)
  const fetchProfile = useAppStore((state) => state.fetchProfile)
  const deleteEvidence = useAppStore((state) => state.deleteEvidence)
  const clearProfile = useAppStore((state) => state.clearProfile)

  useEffect(() => {
    if (open) {
      void fetchProfile()
    }
  }, [fetchProfile, open])

  const confirmClear = () => {
    if (window.confirm('Clear the current profile evidence?')) {
      void clearProfile()
    }
  }

  return (
    <aside
      className={`fixed inset-y-0 right-0 z-40 w-96 max-w-full transform border-l border-stone-200 bg-white text-stone-900 shadow-2xl transition-transform ${
        open ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      <header className="flex h-12 items-center justify-between border-b border-stone-200 px-4">
        <h2 className="text-sm font-semibold">Profile</h2>
        <button className="text-sm text-stone-500 hover:text-emerald-700" onClick={onClose}>
          Close
        </button>
      </header>

      <div className="h-[calc(100vh-3rem)] overflow-y-auto px-4 py-4">
        {!profile ? (
          <p className="text-sm text-stone-500">No active profile yet.</p>
        ) : (
          <div className="space-y-6">
            <ProfileSection title="Skills">
              {Object.entries(profile.skills).map(([name, skill]) => (
                <MetricRow key={name} name={name} count={skill.evidence_count} level={skill.level} />
              ))}
            </ProfileSection>

            <ProfileSection title="Concepts">
              {Object.entries(profile.concepts).map(([id, concept]) => (
                <div key={id} className="border-b border-stone-100 py-2">
                  <MetricRow name={id} count={concept.evidence_count} level={concept.level} />
                  <EvidenceList
                    evidence={concept.evidence ?? []}
                    onDelete={(evidenceId) => void deleteEvidence(evidenceId)}
                  />
                </div>
              ))}
            </ProfileSection>

            <ProfileSection title="Knowledge gaps">
              {profile.knowledge_gaps.map((gap, index) => (
                <div key={gap.id ?? index} className="flex gap-2 border-b border-stone-100 py-2">
                  <p className="min-w-0 flex-1 text-xs text-stone-700">{gap.text}</p>
                  {gap.id && (
                    <button
                      className="text-xs text-pink-700 hover:text-pink-600"
                      onClick={() => void deleteEvidence(gap.id ?? '')}
                    >
                      Delete
                    </button>
                  )}
                </div>
              ))}
            </ProfileSection>

            <ProfileSection title="Recent messages">
              {profile.recent_messages.slice(-8).map((message, index) => (
                <p key={`${index}-${message}`} className="border-b border-stone-100 py-2 font-mono text-xs text-stone-500">
                  {message}
                </p>
              ))}
            </ProfileSection>

            <button
              className="w-full rounded-xl border border-pink-200 px-3 py-2 text-sm text-pink-700 hover:bg-pink-50"
              onClick={confirmClear}
            >
              Clear profile
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}

function ProfileSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase text-stone-500">{title}</h3>
      <div>{children}</div>
    </section>
  )
}

function MetricRow({
  name,
  count,
  level,
}: {
  name: string
  count?: number
  level?: number
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="min-w-0 truncate text-stone-800">{name}</span>
      <span className="shrink-0 font-mono text-xs text-stone-500">
        lvl {level ?? 0} / {count ?? 0}
      </span>
    </div>
  )
}

function EvidenceList({
  evidence,
  onDelete,
}: {
  evidence: ProfileEvidence[]
  onDelete(evidenceId: string): void
}) {
  return (
    <div className="mt-2 space-y-1">
      {evidence.slice(-5).map((item) => (
        <div key={item.id} className="flex gap-2 font-mono text-xs">
          <span className={item.is_gap ? 'text-pink-600' : 'text-emerald-600'}>
            {item.is_gap ? 'gap' : 'hit'}
          </span>
          <span className="min-w-0 flex-1 truncate text-stone-500">{item.context}</span>
          <button className="text-pink-700 hover:text-pink-600" onClick={() => onDelete(item.id)}>
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}
