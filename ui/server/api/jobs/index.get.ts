import { jobsQuerySchema } from '#shared/utils/jobs-query'
import { listJobs } from '~~/server/repositories/jobs'

export default defineEventHandler((event) => {
  const query = parseQuery(event, jobsQuerySchema)
  return listJobs(query)
})
