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
    if (window.confirm('清空画像会删除当前会话记录的画像信息，确认继续？')) {
      void clearProfile()
    }
  }

  return (
    <aside
      className={`fixed inset-y-0 right-0 z-40 w-96 max-w-full transform border-l border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl transition-transform ${
        open ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      <header className="flex h-12 items-center justify-between border-b border-zinc-800 px-4">
        <h2 className="text-sm font-semibold">我的画像</h2>
        <button className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onClose}>
          关闭
        </button>
      </header>

      <div className="h-[calc(100vh-3rem)] overflow-y-auto px-4 py-4">
        {!profile ? (
          <p className="text-sm text-zinc-500">暂无活动会话画像</p>
        ) : (
          <div className="space-y-6">
            <ProfileSection title="Skills">
              {Object.entries(profile.skills).map(([name, skill]) => (
                <MetricRow key={name} name={name} count={skill.evidence_count} level={skill.level} />
              ))}
            </ProfileSection>

            <ProfileSection title="Concepts">
              {Object.entries(profile.concepts).map(([id, concept]) => (
                <div key={id} className="border-b border-zinc-900 py-2">
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
                <div key={gap.id ?? index} className="flex gap-2 border-b border-zinc-900 py-2">
                  <p className="min-w-0 flex-1 text-xs text-zinc-300">{gap.text}</p>
                  {gap.id && (
                    <button
                      className="text-xs text-red-300 hover:text-red-200"
                      onClick={() => void deleteEvidence(gap.id ?? '')}
                    >
                      删除
                    </button>
                  )}
                </div>
              ))}
            </ProfileSection>

            <ProfileSection title="Recent messages">
              {profile.recent_messages.slice(-8).map((message, index) => (
                <p key={`${index}-${message}`} className="border-b border-zinc-900 py-2 text-xs text-zinc-400">
                  {message}
                </p>
              ))}
            </ProfileSection>

            <button
              className="w-full rounded border border-red-800 px-3 py-2 text-sm text-red-200 hover:bg-red-950"
              onClick={confirmClear}
            >
              清空画像
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
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-normal text-zinc-500">{title}</h3>
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
      <span className="min-w-0 truncate text-zinc-200">{name}</span>
      <span className="shrink-0 text-xs text-zinc-500">
        lvl {level ?? 0} · {count ?? 0}
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
        <div key={item.id} className="flex gap-2 text-xs">
          <span className={item.is_gap ? 'text-amber-300' : 'text-emerald-300'}>
            {item.is_gap ? 'gap' : 'hit'}
          </span>
          <span className="min-w-0 flex-1 truncate text-zinc-500">{item.context}</span>
          <button className="text-red-300 hover:text-red-200" onClick={() => onDelete(item.id)}>
            删除
          </button>
        </div>
      ))}
    </div>
  )
}
