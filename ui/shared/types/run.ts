export interface RunSource {
  source: string
  fetched: number
  durationS: number
  error: string | null
  /** True when this source returned nothing but usually returns results. */
  suspicious: boolean
}

export interface Run {
  id: number
  startedAt: string
  finishedAt: string | null
  dryRun: boolean
  fetched: number
  kept: number
  uniqueCount: number
  newCount: number
  notified: boolean
  errors: string[]
  durationS: number | null
  sources: RunSource[]
}

export type RunnerStatus = 'idle' | 'running' | 'succeeded' | 'failed'

export interface RunnerState {
  status: RunnerStatus
  command: string | null
  startedAt: string | null
  finishedAt: string | null
  exitCode: number | null
  /** Last lines of combined stdout/stderr. */
  log: string[]
}
