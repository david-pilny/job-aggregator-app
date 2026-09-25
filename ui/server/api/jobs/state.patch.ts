import { z } from 'zod'
import { JOB_STATUSES } from '#shared/types/job'
import { setStatusBulk } from '~~/server/repositories/job-state'

const body = z.object({
  ids: z.array(z.string().regex(/^[0-9a-f]{16}$/)).min(1).max(500),
  status: z.enum(JOB_STATUSES)
})

/** Bulk status change (e.g. mark a whole page as seen). */
export default defineEventHandler(async (event) => {
  const { ids, status } = await parseBody(event, body)
  return { updated: setStatusBulk(ids, status), status }
})
