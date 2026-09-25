import type { JobsFacets, JobsPage } from '#shared/types/job'
import { parseJobsQuery, serializeJobsQuery, type JobsQuery } from '#shared/utils/jobs-query'

const EMPTY_PAGE: JobsPage = { items: [], total: 0, page: 1, pageSize: 50 }

/**
 * The jobs list is driven entirely by the URL: filters live in `route.query`,
 * the fetch re-runs whenever the parsed query changes, and `update()` writes
 * back only non-default values so links stay short and survive a refresh.
 */
export function useJobs() {
  const route = useRoute()
  const router = useRouter()

  const query = computed<JobsQuery>(() => parseJobsQuery(route.query))

  const { data, status, error, refresh } = useFetch<JobsPage>('/api/jobs', {
    query,
    default: () => EMPTY_PAGE,
    lazy: true
  })

  function update(patch: Partial<JobsQuery>) {
    const next: JobsQuery = { ...query.value, ...patch }
    // Any filter change resets pagination unless the caller is paging.
    if (!('page' in patch)) next.page = 1
    return router.replace({ query: serializeJobsQuery(next) })
  }

  function reset() {
    return router.replace({ query: {} })
  }

  const pageCount = computed(() => Math.max(1, Math.ceil(data.value.total / query.value.pageSize)))

  return { query, data, status, error, refresh, update, reset, pageCount }
}

export function useJobsFacets() {
  return useFetch<JobsFacets>('/api/jobs/facets', {
    key: 'jobs-facets',
    default: () => ({ sources: [], tags: [], statuses: [], remoteTypes: [] }),
    lazy: true
  })
}
