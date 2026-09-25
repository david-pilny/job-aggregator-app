import type { JobStatus } from '../types/job'

/** Kanban stages, left to right. Other statuses (new/seen/not interested) stay in the list view. */
export const TRACKER_STAGES = ['saved', 'applied', 'interviewing', 'offer', 'rejected'] as const satisfies readonly JobStatus[]
export type TrackerStage = (typeof TRACKER_STAGES)[number]
