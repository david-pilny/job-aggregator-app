import { z } from 'zod'
import { JOB_STATUSES } from '#shared/types/job'
import { upsertJobState } from '~~/server/repositories/job-state'

const params = z.object({ id: z.string().regex(/^[0-9a-f]{16}$/) })
const body = z.object({
  status: z.enum(JOB_STATUSES).optional(),
  notes: z.string().max(20000).nullable().optional(),
  appliedAt: z.string().datetime({ offset: true }).nullable().optional()
}).refine(b => b.status !== undefined || b.notes !== undefined || b.appliedAt !== undefined, {
  message: 'Nothing to update'
})

export default defineEventHandler(async (event) => {
  const { id } = parseParams(event, params)
  const patch = await parseBody(event, body)
  return upsertJobState(id, patch)
})
