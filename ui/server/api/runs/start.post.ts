import { z } from 'zod'

const body = z.object({ dryRun: z.boolean().default(false) })

export default defineEventHandler(async (event) => {
  const { dryRun } = await parseBody(event, body)
  return startPipeline({ dryRun })
})
