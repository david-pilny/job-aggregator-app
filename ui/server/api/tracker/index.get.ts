import { TRACKER_STAGES } from '#shared/utils/tracker'
import { listByStatuses } from '~~/server/repositories/jobs'

export default defineEventHandler(() => ({ items: listByStatuses([...TRACKER_STAGES]) }))
