import { z } from 'zod'
import { getJob } from '~~/server/repositories/jobs'

const params = z.object({ id: z.string().regex(/^[0-9a-f]{16}$/) })

export default defineEventHandler((event) => {
  const { id } = parseParams(event, params)
  const job = getJob(id)
  if (!job) throw createError({ statusCode: 404, statusMessage: 'Job not found' })
  return job
})
