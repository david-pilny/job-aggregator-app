import type { Run, RunSource } from '#shared/types/run'

interface RunRow {
  id: number
  started_at: string
  finished_at: string | null
  dry_run: number
  fetched: number
  kept: number
  unique_count: number
  new_count: number
  notified: number
  errors: string
}

interface RunSourceRow {
  run_id: number
  source: string
  fetched: number
  duration_s: number
  error: string | null
}

/** A source that averaged at least this many results before is flagged when it returns 0. */
const SUSPICIOUS_MIN_AVG = 3
const HISTORY_RUNS = 5

function durationSeconds(row: RunRow): number | null {
  if (!row.finished_at) return null
  return Math.round((Date.parse(row.finished_at) - Date.parse(row.started_at)) / 1000)
}

/**
 * Recent runs with their per-source results. The "suspicious" flag mirrors
 * the pipeline's health check: zero results from a source whose previous runs
 * averaged a few or more.
 */
export function listRuns(limit: number): Run[] {
  const db = useDb()
  const runs = db.prepare('SELECT * FROM runs ORDER BY id DESC LIMIT ?').all(limit) as RunRow[]
  if (!runs.length) return []

  const minId = runs[runs.length - 1]!.id
  const sourceRows = db
    .prepare('SELECT * FROM run_sources WHERE run_id >= ? ORDER BY run_id ASC, source ASC')
    .all(minId) as RunSourceRow[]
  // Prior runs beyond the window, so the oldest visible run also gets a fair average.
  const history = db
    .prepare(`SELECT * FROM run_sources WHERE run_id < ? AND run_id >= ? ORDER BY run_id ASC`)
    .all(minId, minId - HISTORY_RUNS) as RunSourceRow[]

  const bySource = new Map<string, RunSourceRow[]>()
  for (const row of [...history, ...sourceRows]) {
    const list = bySource.get(row.source) ?? []
    list.push(row)
    bySource.set(row.source, list)
  }

  function suspicious(row: RunSourceRow): boolean {
    if (row.fetched > 0 || row.error) return false
    const previous = (bySource.get(row.source) ?? [])
      .filter(r => r.run_id < row.run_id)
      .slice(-HISTORY_RUNS)
    if (!previous.length) return false
    const avg = previous.reduce((sum, r) => sum + r.fetched, 0) / previous.length
    return avg >= SUSPICIOUS_MIN_AVG
  }

  const sourcesByRun = new Map<number, RunSource[]>()
  for (const row of sourceRows) {
    const list = sourcesByRun.get(row.run_id) ?? []
    list.push({
      source: row.source,
      fetched: row.fetched,
      durationS: row.duration_s,
      error: row.error,
      suspicious: suspicious(row)
    })
    sourcesByRun.set(row.run_id, list)
  }

  return runs.map(row => ({
    id: row.id,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
    dryRun: !!row.dry_run,
    fetched: row.fetched,
    kept: row.kept,
    uniqueCount: row.unique_count,
    newCount: row.new_count,
    notified: !!row.notified,
    errors: JSON.parse(row.errors || '[]'),
    durationS: durationSeconds(row),
    sources: sourcesByRun.get(row.id) ?? []
  }))
}
