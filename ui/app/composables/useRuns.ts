import type { Run, RunnerState } from '#shared/types/run'

const IDLE: RunnerState = {
  status: 'idle',
  command: null,
  startedAt: null,
  finishedAt: null,
  exitCode: null,
  log: []
}

export function useRuns(limit = 20) {
  const toast = useToast()

  const runs = useFetch<{ items: Run[] }>('/api/runs', {
    key: `runs-${limit}`,
    query: { limit },
    default: () => ({ items: [] }),
    lazy: true
  })

  const runner = useFetch<RunnerState>('/api/runs/current', {
    key: 'runner',
    default: () => IDLE,
    lazy: true,
    server: false
  })

  const isRunning = computed(() => runner.data.value.status === 'running')

  /**
   * Poll the runner while a run is in progress. The log is small (bounded on
   * the server), so re-fetching the whole state every 2 s is simpler and more
   * robust than a streaming connection for a single local user.
   */
  let timer: ReturnType<typeof setInterval> | undefined
  function poll() {
    stopPolling()
    timer = setInterval(async () => {
      await runner.refresh()
      if (!isRunning.value) {
        stopPolling()
        await runs.refresh()
        const { status, exitCode } = runner.data.value
        toast.add({
          title: status === 'succeeded' ? 'Pipeline run finished' : `Pipeline run failed (exit ${exitCode})`,
          color: status === 'succeeded' ? 'success' : 'error',
          icon: status === 'succeeded' ? 'i-lucide-check' : 'i-lucide-triangle-alert'
        })
        await refreshNuxtData(['jobs-facets', 'tracker'])
      }
    }, 2000)
  }
  function stopPolling() {
    if (timer) clearInterval(timer)
    timer = undefined
  }
  watch(isRunning, running => running ? poll() : stopPolling(), { immediate: true })
  onScopeDispose(stopPolling)

  async function start(dryRun: boolean) {
    try {
      runner.data.value = await $fetch<RunnerState>('/api/runs/start', { method: 'POST', body: { dryRun } })
      toast.add({ title: dryRun ? 'Dry run started' : 'Pipeline run started', icon: 'i-lucide-play' })
    } catch (error) {
      toast.add({ title: 'Could not start the run', description: String(error), color: 'error', icon: 'i-lucide-triangle-alert' })
    }
  }

  return { runs: runs.data, runsStatus: runs.status, refreshRuns: runs.refresh, runner: runner.data, isRunning, start }
}
