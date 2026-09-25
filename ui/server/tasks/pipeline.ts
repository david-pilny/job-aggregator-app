/**
 * Scheduled pipeline run. Nitro's cron runner (see `scheduledTasks` in
 * nuxt.config.ts) calls this while the UI server is up, so `pnpm dev` alone
 * keeps the database fresh. It reuses the same single-run guard as "Run now",
 * so a scheduled tick never overlaps a manual run.
 */
export default defineTask({
  meta: {
    name: 'pipeline',
    description: 'Run the Python job pipeline (jobs run)'
  },
  run() {
    if (isRunning()) {
      return { result: 'skipped: a run is already in progress' }
    }
    const state = startPipeline({ dryRun: false })
    return { result: `started at ${state.startedAt}: ${state.command}` }
  }
})
