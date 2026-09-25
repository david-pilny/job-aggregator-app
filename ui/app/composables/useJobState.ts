import type { JobListItem, JobState, JobStatus } from '#shared/types/job'

export const STATUS_LABELS: Record<JobStatus, string> = {
  new: 'New',
  seen: 'Seen',
  saved: 'Saved',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
  not_interested: 'Not interested'
}

interface Patch {
  status?: JobStatus
  notes?: string | null
  appliedAt?: string | null
}

/**
 * Status/notes writes with optimistic updates: the rows passed in are mutated
 * immediately, the PATCH runs in the background, and the previous values are
 * restored (with a toast) if it fails.
 */
export function useJobState() {
  const toast = useToast()
  const pending = ref(false)

  async function patch(job: JobListItem, changes: Patch, { silent = false } = {}): Promise<JobState | null> {
    const previous = { status: job.status, notes: job.notes, appliedAt: job.appliedAt }
    if (changes.status !== undefined) job.status = changes.status
    if (changes.notes !== undefined) job.notes = changes.notes
    if (changes.appliedAt !== undefined) job.appliedAt = changes.appliedAt
    pending.value = true
    try {
      const state = await $fetch<JobState>(`/api/jobs/${job.id}/state`, { method: 'PATCH', body: changes })
      job.status = state.status
      job.notes = state.notes
      job.appliedAt = state.appliedAt
      if (!silent && changes.status) {
        toast.add({ title: STATUS_LABELS[changes.status], description: job.title, icon: 'i-lucide-check' })
      }
      return state
    } catch (error) {
      Object.assign(job, previous)
      toast.add({ title: 'Update failed', description: String(error), color: 'error', icon: 'i-lucide-triangle-alert' })
      return null
    } finally {
      pending.value = false
    }
  }

  async function setStatusMany(jobs: JobListItem[], status: JobStatus): Promise<number> {
    const previous = jobs.map(j => j.status)
    for (const job of jobs) {
      job.status = status
    }
    try {
      const result = await $fetch<{ updated: number }>('/api/jobs/state', {
        method: 'PATCH',
        body: { ids: jobs.map(j => j.id), status }
      })
      toast.add({ title: `${result.updated} job(s) marked ${STATUS_LABELS[status].toLowerCase()}`, icon: 'i-lucide-check' })
      return result.updated
    } catch (error) {
      jobs.forEach((j, i) => {
        j.status = previous[i]!
      })
      toast.add({ title: 'Bulk update failed', description: String(error), color: 'error', icon: 'i-lucide-triangle-alert' })
      return 0
    }
  }

  return { patch, setStatusMany, pending }
}
