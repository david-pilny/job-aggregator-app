import type { JobState, JobStatus } from '#shared/types/job'

/** The `job_state` table: the UI's own progress tracking, keyed by jobs.id. */

interface StateRow {
  job_id: string
  status: JobStatus
  notes: string | null
  applied_at: string | null
  updated_at: string
}

export interface StatePatch {
  status?: JobStatus
  notes?: string | null
  appliedAt?: string | null
}

function toState(row: StateRow): JobState {
  return {
    jobId: row.job_id,
    status: row.status,
    notes: row.notes,
    appliedAt: row.applied_at,
    updatedAt: row.updated_at
  }
}

export function getJobState(jobId: string): JobState | null {
  const row = useDb().prepare('SELECT * FROM job_state WHERE job_id = ?').get(jobId) as StateRow | undefined
  return row ? toState(row) : null
}

/**
 * Upsert one job's state. Moving to `applied` stamps `applied_at` unless the
 * caller supplies one; other fields are only touched when present in the patch.
 */
export function upsertJobState(jobId: string, patch: StatePatch): JobState {
  const db = useDb()
  const exists = db.prepare('SELECT 1 FROM jobs WHERE id = ?').get(jobId)
  if (!exists) throw createError({ statusCode: 404, statusMessage: `Job ${jobId} not found` })

  const now = new Date().toISOString()
  const current = getJobState(jobId)
  const status = patch.status ?? current?.status ?? 'new'
  const appliedAt = patch.appliedAt !== undefined
    ? patch.appliedAt
    : (status === 'applied' && !current?.appliedAt ? now : current?.appliedAt ?? null)
  const notes = patch.notes !== undefined ? patch.notes : current?.notes ?? null

  db.prepare(`
    INSERT INTO job_state (job_id, status, notes, applied_at, updated_at)
    VALUES (@jobId, @status, @notes, @appliedAt, @now)
    ON CONFLICT(job_id) DO UPDATE SET
      status = excluded.status, notes = excluded.notes,
      applied_at = excluded.applied_at, updated_at = excluded.updated_at
  `).run({ jobId, status, notes, appliedAt, now })
  return getJobState(jobId)!
}

export function setStatusBulk(jobIds: string[], status: JobStatus): number {
  const db = useDb()
  const run = db.transaction((ids: string[]) => {
    let n = 0
    for (const id of ids) {
      if (!db.prepare('SELECT 1 FROM jobs WHERE id = ?').get(id)) continue
      upsertJobState(id, { status })
      n++
    }
    return n
  })
  return run(jobIds)
}
