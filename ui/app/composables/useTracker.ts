import type { JobListItem, JobStatus } from '#shared/types/job'
import { TRACKER_STAGES, type TrackerStage } from '#shared/utils/tracker'

export const STAGE_ICONS: Record<TrackerStage, string> = {
  saved: 'i-lucide-bookmark',
  applied: 'i-lucide-send',
  interviewing: 'i-lucide-messages-square',
  offer: 'i-lucide-party-popper',
  rejected: 'i-lucide-circle-x'
}

/**
 * One flat fetch of every tracked job; columns are a computed grouping, so an
 * optimistic status change (which mutates the row) moves the card instantly.
 */
export function useTracker() {
  const { data, status, refresh } = useFetch<{ items: JobListItem[] }>('/api/tracker', {
    key: 'tracker',
    default: () => ({ items: [] }),
    lazy: true
  })
  const { patch } = useJobState()

  const columns = computed(() =>
    TRACKER_STAGES.map(stage => ({
      stage,
      items: data.value.items.filter(job => job.status === stage)
    }))
  )

  async function move(job: JobListItem, status: JobStatus) {
    if (job.status === status) return
    await patch(job, { status })
    // Leaving the tracked stages removes the card once the server confirms.
    if (!(TRACKER_STAGES as readonly string[]).includes(job.status)) {
      data.value.items = data.value.items.filter(j => j.id !== job.id)
    }
  }

  return { data, status, refresh, columns, move }
}
