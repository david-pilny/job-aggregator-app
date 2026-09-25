import { z } from 'zod'
import { listRuns } from '~~/server/repositories/runs'

const query = z.object({ limit: z.coerce.number().int().min(1).max(100).default(20) })

export default defineEventHandler((event) => {
  const { limit } = parseQuery(event, query)
  return { items: listRuns(limit) }
})
