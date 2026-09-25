/** Types shared by server routes and the client. Mirrors the pipeline's SQLite schema. */

export const JOB_STATUSES = [
  'new',
  'seen',
  'saved',
  'applied',
  'interviewing',
  'offer',
  'rejected',
  'not_interested'
] as const
export type JobStatus = (typeof JOB_STATUSES)[number]

export const REMOTE_TYPES = ['remote', 'hybrid', 'onsite', 'unknown'] as const
export type RemoteType = (typeof REMOTE_TYPES)[number]

export type SalaryPeriod = 'year' | 'month' | 'week' | 'day' | 'hour'

export interface JobSourceRef {
  source: string
  url: string
}

/** Row shape returned by the list endpoint; description is left out on purpose. */
export interface JobListItem {
  id: string
  title: string
  company: string
  location: string | null
  remoteType: RemoteType
  salaryMin: number | null
  salaryMax: number | null
  salaryCurrency: string | null
  salaryPeriod: SalaryPeriod | null
  techTags: string[]
  language: string
  postedAt: string | null
  firstSeenAt: string
  lastSeenAt: string
  score: number | null
  sources: JobSourceRef[]
  status: JobStatus
  notes: string | null
  appliedAt: string | null
}

export interface JobDetail extends JobListItem {
  description: string
  scoreBreakdown: Record<string, number>
  primarySource: string
  primaryUrl: string
  stateUpdatedAt: string | null
}

/** The one table the UI owns; the Python pipeline never touches it. */
export interface JobState {
  jobId: string
  status: JobStatus
  notes: string | null
  appliedAt: string | null
  updatedAt: string
}

export interface JobsPage {
  items: JobListItem[]
  total: number
  page: number
  pageSize: number
}

export interface JobsFacets {
  sources: { source: string, count: number }[]
  tags: { tag: string, count: number }[]
  statuses: { status: JobStatus, count: number }[]
  remoteTypes: { remoteType: RemoteType, count: number }[]
}
