import { z } from 'zod'
import { JOB_STATUSES, REMOTE_TYPES } from '../types/job'

/**
 * Query-string contract for the jobs list. Shared so the page can parse
 * `route.query` with the same defaults the server applies, and serialize only
 * the non-default values back into a shareable URL.
 */

export const JOB_SORTS = ['score', 'posted', 'salary', 'seen'] as const
export type JobSort = (typeof JOB_SORTS)[number]

const csv = <T extends z.ZodType>(item: T) =>
  z.preprocess((value) => {
    if (value == null || value === '') return []
    const raw = Array.isArray(value) ? value : String(value).split(',')
    return raw.map(v => String(v).trim()).filter(Boolean)
  }, z.array(item))

export const jobsQuerySchema = z.object({
  q: z.string().trim().max(200).default(''),
  minScore: z.coerce.number().min(0).max(100).default(0),
  remote: csv(z.enum(REMOTE_TYPES)).default([]),
  source: csv(z.string().max(60)).default([]),
  tags: csv(z.string().max(40)).default([]),
  status: csv(z.enum(JOB_STATUSES)).default([]),
  /** Posted (or first seen, when the board gives no date) within the last N days; 0 = any. */
  days: z.coerce.number().int().min(0).max(365).default(0),
  /** Include jobs the pipeline has not seen for a while (default: last 30 days only). */
  stale: z.coerce.boolean().default(false),
  sort: z.enum(JOB_SORTS).default('score'),
  dir: z.enum(['asc', 'desc']).default('desc'),
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(10).max(200).default(50)
})

export type JobsQuery = z.infer<typeof jobsQuerySchema>
export type JobsQueryInput = z.input<typeof jobsQuerySchema>

export const JOBS_QUERY_DEFAULTS: JobsQuery = jobsQuerySchema.parse({})

/** Parse loosely-typed route/query params; invalid values fall back to defaults per field. */
export function parseJobsQuery(raw: Record<string, unknown>): JobsQuery {
  const result = jobsQuerySchema.safeParse(raw)
  if (result.success) return result.data
  const invalid = new Set(result.error.issues.map(issue => issue.path[0]).filter(k => typeof k === 'string'))
  const cleaned = Object.fromEntries(Object.entries(raw).filter(([key]) => !invalid.has(key)))
  return jobsQuerySchema.parse(cleaned)
}

/** Only non-default values, arrays joined with commas, so the URL stays readable. */
export function serializeJobsQuery(query: JobsQuery): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(query) as [keyof JobsQuery, unknown][]) {
    const fallback = JOBS_QUERY_DEFAULTS[key]
    if (Array.isArray(value)) {
      if (value.length) out[key] = value.join(',')
    } else if (value !== fallback && value !== '' && value != null) {
      out[key] = String(value)
    }
  }
  return out
}
