import { formatDistanceToNowStrict, parseISO } from 'date-fns'
import type { JobListItem, JobStatus, RemoteType } from '#shared/types/job'

type BadgeColor = 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error' | 'neutral'

export function scoreColor(score: number | null): BadgeColor {
  if (score == null) return 'neutral'
  if (score >= 80) return 'success'
  if (score >= 60) return 'primary'
  if (score >= 40) return 'warning'
  return 'neutral'
}

export const REMOTE_LABELS: Record<RemoteType, string> = {
  remote: 'Remote',
  hybrid: 'Hybrid',
  onsite: 'On-site',
  unknown: 'Unknown'
}

export const REMOTE_COLORS: Record<RemoteType, BadgeColor> = {
  remote: 'success',
  hybrid: 'info',
  onsite: 'warning',
  unknown: 'neutral'
}

export const STATUS_COLORS: Record<JobStatus, BadgeColor> = {
  new: 'neutral',
  seen: 'neutral',
  saved: 'info',
  applied: 'primary',
  interviewing: 'warning',
  offer: 'success',
  rejected: 'error',
  not_interested: 'neutral'
}

const PERIOD_SUFFIX: Record<string, string> = {
  year: '/yr',
  month: '/mo',
  week: '/wk',
  day: '/day',
  hour: '/h'
}

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })

export function formatSalary(job: Pick<JobListItem, 'salaryMin' | 'salaryMax' | 'salaryCurrency' | 'salaryPeriod'>): string {
  const { salaryMin: min, salaryMax: max } = job
  if (min == null && max == null) return ''
  const range = min != null && max != null && min !== max
    ? `${compact.format(min)}–${compact.format(max)}`
    : min != null && max == null
      ? `from ${compact.format(min)}`
      : max != null && min == null
        ? `up to ${compact.format(max)}`
        : compact.format((min ?? max)!)
  const suffix = job.salaryPeriod ? PERIOD_SUFFIX[job.salaryPeriod] ?? '' : ''
  return `${range} ${job.salaryCurrency ?? ''}${suffix}`.trim()
}

export function formatRelative(iso: string | null): string {
  if (!iso) return ''
  try {
    return formatDistanceToNowStrict(parseISO(iso), { addSuffix: true })
  } catch {
    return iso
  }
}

export function formatDate(iso: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}

/** Icon per source; boards without a brand icon get a generic one. */
export function sourceIcon(source: string): string {
  switch (source) {
    case 'linkedin': return 'i-simple-icons-linkedin'
    case 'indeed': return 'i-simple-icons-indeed'
    case 'google': return 'i-simple-icons-google'
    case 'welcometothejungle.com': return 'i-simple-icons-welcometothejungle'
    case 'remotive.com':
    case 'weworkremotely.com':
    case 'arbeitnow.com':
      return 'i-lucide-globe'
    default: return 'i-lucide-briefcase'
  }
}

export function sourceLabel(source: string): string {
  return source.replace(/\.(cz|com|it)$/, '')
}
