import type { JobDetail, JobListItem, JobsFacets, JobsPage, JobStatus, RemoteType, SalaryPeriod } from '#shared/types/job'
import type { JobsQuery } from '#shared/utils/jobs-query'

/** All SQL for reading the pipeline's `jobs` tables lives here; routes stay thin. */

interface JobRow {
  id: string
  title: string
  company: string
  location: string | null
  remote_type: RemoteType
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  salary_period: SalaryPeriod | null
  tech_tags: string
  language: string
  posted_at: string | null
  first_seen_at: string
  last_seen_at: string
  score: number | null
  sources_json: string | null
  status: JobStatus | null
  notes: string | null
  applied_at: string | null
}

interface JobDetailRow extends JobRow {
  description: string
  score_breakdown: string
  source: string
  source_url: string
  state_updated_at: string | null
}

const LIST_COLUMNS = `
  j.id, j.title, j.company, j.location, j.remote_type, j.salary_min, j.salary_max,
  j.salary_currency, j.salary_period, j.tech_tags, j.language, j.posted_at,
  j.first_seen_at, j.last_seen_at, j.score,
  (SELECT json_group_array(json_object('source', s.source, 'url', s.url))
     FROM job_sources s WHERE s.job_id = j.id) AS sources_json,
  st.status, st.notes, st.applied_at`

const SORT_SQL: Record<JobsQuery['sort'], string> = {
  score: 'j.score',
  posted: `COALESCE(j.posted_at, substr(j.first_seen_at, 1, 10))`,
  salary: 'COALESCE(j.salary_max, j.salary_min)',
  seen: 'j.first_seen_at'
}

function toListItem(row: JobRow): JobListItem {
  return {
    id: row.id,
    title: row.title,
    company: row.company,
    location: row.location,
    remoteType: row.remote_type,
    salaryMin: row.salary_min,
    salaryMax: row.salary_max,
    salaryCurrency: row.salary_currency,
    salaryPeriod: row.salary_period,
    techTags: JSON.parse(row.tech_tags || '[]'),
    language: row.language,
    postedAt: row.posted_at,
    firstSeenAt: row.first_seen_at,
    lastSeenAt: row.last_seen_at,
    score: row.score,
    sources: JSON.parse(row.sources_json || '[]'),
    status: row.status ?? 'new',
    notes: row.notes,
    appliedAt: row.applied_at
  }
}

function buildWhere(query: JobsQuery): { sql: string, params: unknown[] } {
  const clauses: string[] = []
  const params: unknown[] = []

  if (query.q) {
    const like = `%${query.q}%`
    clauses.push('(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)')
    params.push(like, like, like)
  }
  if (query.minScore > 0) {
    clauses.push('j.score >= ?')
    params.push(query.minScore)
  }
  if (query.remote.length) {
    clauses.push(`j.remote_type IN (${placeholders(query.remote.length)})`)
    params.push(...query.remote)
  }
  if (query.source.length) {
    clauses.push(`EXISTS (SELECT 1 FROM job_sources s WHERE s.job_id = j.id
      AND s.source IN (${placeholders(query.source.length)}))`)
    params.push(...query.source)
  }
  if (query.tags.length) {
    clauses.push(`EXISTS (SELECT 1 FROM json_each(j.tech_tags) t
      WHERE t.value IN (${placeholders(query.tags.length)}))`)
    params.push(...query.tags)
  }
  if (query.status.length) {
    clauses.push(`COALESCE(st.status, 'new') IN (${placeholders(query.status.length)})`)
    params.push(...query.status)
  }
  if (query.days > 0) {
    clauses.push(`COALESCE(j.posted_at, substr(j.first_seen_at, 1, 10)) >= date('now', ?)`)
    params.push(`-${query.days} days`)
  }
  if (!query.stale) {
    clauses.push(`j.last_seen_at >= datetime('now', '-30 days')`)
  }
  return { sql: clauses.length ? `WHERE ${clauses.join(' AND ')}` : '', params }
}

function placeholders(n: number): string {
  return Array.from({ length: n }, () => '?').join(',')
}

export function listJobs(query: JobsQuery): JobsPage {
  const db = useDb()
  const where = buildWhere(query)
  const from = `FROM jobs j LEFT JOIN job_state st ON st.job_id = j.id ${where.sql}`
  const order = `ORDER BY ${SORT_SQL[query.sort]} ${query.dir === 'asc' ? 'ASC' : 'DESC'} NULLS LAST,
    j.first_seen_at DESC, j.id`
  const offset = (query.page - 1) * query.pageSize

  const total = db.prepare(`SELECT COUNT(*) AS n ${from}`).get(...where.params) as { n: number }
  const rows = db
    .prepare(`SELECT ${LIST_COLUMNS} ${from} ${order} LIMIT ? OFFSET ?`)
    .all(...where.params, query.pageSize, offset) as JobRow[]

  return { items: rows.map(toListItem), total: total.n, page: query.page, pageSize: query.pageSize }
}

export function getJob(id: string): JobDetail | null {
  const row = useDb()
    .prepare(`SELECT ${LIST_COLUMNS}, j.description, j.score_breakdown, j.source, j.source_url,
        st.updated_at AS state_updated_at
      FROM jobs j LEFT JOIN job_state st ON st.job_id = j.id WHERE j.id = ?`)
    .get(id) as JobDetailRow | undefined
  if (!row) return null
  return {
    ...toListItem(row),
    description: row.description,
    scoreBreakdown: JSON.parse(row.score_breakdown || '{}'),
    primarySource: row.source,
    primaryUrl: row.source_url,
    stateUpdatedAt: row.state_updated_at
  }
}

export function getFacets(): JobsFacets {
  const db = useDb()
  const sources = db.prepare(`SELECT source, COUNT(DISTINCT job_id) AS count FROM job_sources
    GROUP BY source ORDER BY count DESC`).all() as JobsFacets['sources']
  const tags = db.prepare(`SELECT t.value AS tag, COUNT(*) AS count
    FROM jobs j, json_each(j.tech_tags) t GROUP BY t.value ORDER BY count DESC LIMIT 60`)
    .all() as JobsFacets['tags']
  const statuses = db.prepare(`SELECT COALESCE(st.status, 'new') AS status, COUNT(*) AS count
    FROM jobs j LEFT JOIN job_state st ON st.job_id = j.id GROUP BY 1 ORDER BY count DESC`)
    .all() as JobsFacets['statuses']
  const remoteTypes = db.prepare(`SELECT remote_type AS remoteType, COUNT(*) AS count
    FROM jobs GROUP BY 1 ORDER BY count DESC`).all() as JobsFacets['remoteTypes']
  return { sources, tags, statuses, remoteTypes }
}
