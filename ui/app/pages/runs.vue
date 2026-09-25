<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { Run } from '#shared/types/run'

useDashboard()
useSeoMeta({ title: 'Sources & runs' })

const UBadge = resolveComponent('UBadge')
const UTooltip = resolveComponent('UTooltip')

const { runs, runsStatus, runner, isRunning, start } = useRuns(20)

const dryRun = ref(true)
const { pipelineSchedule } = useRuntimeConfig().public

// --- live log: stick to the bottom while lines arrive ---------------------------------

const logEl = useTemplateRef<HTMLElement>('logEl')
watch(() => runner.value.log.length, async () => {
  await nextTick()
  logEl.value?.scrollTo({ top: logEl.value.scrollHeight })
})

const runnerColor = computed(() => ({
  idle: 'neutral',
  running: 'primary',
  succeeded: 'success',
  failed: 'error'
} as const)[runner.value.status])

// --- runs table -------------------------------------------------------------------------

/** Every source seen in the window, in a stable order, so the matrix columns line up. */
const sourceNames = computed(() => {
  const names = new Set<string>()
  for (const run of runs.value.items) for (const s of run.sources) names.add(s.source)
  return [...names].sort()
})

const suspiciousCount = computed(() =>
  runs.value.items[0]?.sources.filter(s => s.suspicious || s.error).length ?? 0
)

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '…'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m ? `${m}m ${s}s` : `${s}s`
}

const baseColumns: TableColumn<Run>[] = [
  {
    accessorKey: 'startedAt',
    header: 'Started',
    cell: ({ row }) => h('div', undefined, [
      h('p', { class: 'font-medium text-highlighted whitespace-nowrap' }, formatRelative(row.original.startedAt)),
      h('p', { class: 'text-xs text-muted whitespace-nowrap' }, [
        row.original.startedAt.slice(0, 16).replace('T', ' '),
        row.original.dryRun ? ' · dry run' : ''
      ])
    ])
  },
  {
    accessorKey: 'durationS',
    header: 'Duration',
    cell: ({ row }) => h('span', { class: 'tabular-nums' }, formatDuration(row.original.durationS))
  },
  {
    id: 'counts',
    header: 'Fetched → kept → unique → new',
    cell: ({ row }) => {
      const r = row.original
      return h('span', { class: 'tabular-nums whitespace-nowrap' }, [
        `${r.fetched} → ${r.kept} → ${r.uniqueCount} → `,
        h('strong', { class: r.newCount ? 'text-highlighted' : '' }, String(r.newCount))
      ])
    }
  },
  {
    accessorKey: 'errors',
    header: 'Errors',
    cell: ({ row }) => {
      const errors = row.original.errors
      if (!errors.length) return h('span', { class: 'text-muted' }, '–')
      return h(UTooltip, { text: errors.join('\n') }, () =>
        h(UBadge, { color: 'error', variant: 'subtle', size: 'sm' }, () => `${errors.length}`))
    }
  }
]

const columns = computed<TableColumn<Run>[]>(() => [
  ...baseColumns,
  ...sourceNames.value.map<TableColumn<Run>>(name => ({
    id: `src-${name}`,
    header: () => h('span', { class: 'text-xs', title: name }, sourceLabel(name)),
    cell: ({ row }) => {
      const result = row.original.sources.find(s => s.source === name)
      if (!result) return h('span', { class: 'text-muted' }, '–')
      const flagged = result.suspicious || !!result.error
      const badge = h(UBadge, {
        color: result.error ? 'error' : result.suspicious ? 'warning' : result.fetched ? 'neutral' : 'neutral',
        variant: flagged ? 'solid' : 'subtle',
        size: 'sm',
        class: 'tabular-nums'
      }, () => String(result.fetched))
      return flagged
        ? h(UTooltip, { text: result.error ?? 'Returned 0 results but usually returns some' }, () => badge)
        : badge
    }
  }))
])
</script>

<template>
  <UDashboardPanel id="runs">
    <template #header>
      <UDashboardNavbar title="Sources & runs" :ui="{ right: 'gap-3' }">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UTooltip :text="pipelineSchedule ? 'Runs automatically while the UI server is up (NUXT_PIPELINE_SCHEDULE)' : 'No schedule: set NUXT_PIPELINE_SCHEDULE'">
            <UBadge
              color="neutral"
              variant="subtle"
              size="sm"
              icon="i-lucide-clock"
            >
              {{ pipelineSchedule ? `schedule ${pipelineSchedule}` : 'no schedule' }}
            </UBadge>
          </UTooltip>
          <UCheckbox
            v-model="dryRun"
            label="Dry run (no email)"
            size="sm"
            :disabled="isRunning"
          />
          <UButton
            :label="isRunning ? 'Running…' : 'Run now'"
            :icon="isRunning ? 'i-lucide-loader-circle' : 'i-lucide-play'"
            :loading="isRunning"
            :disabled="isRunning"
            @click="start(dryRun)"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="suspiciousCount"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :title="`${suspiciousCount} source(s) look broken in the latest run`"
        description="Highlighted cells returned nothing although they usually do, or failed with an error. Check the log or the adapter."
      />

      <!-- Runner panel -->
      <UCard v-if="runner.status !== 'idle'" :ui="{ body: 'p-0 sm:p-0' }">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-sm">
              <UBadge :color="runnerColor" variant="subtle" class="capitalize">
                {{ runner.status }}
              </UBadge>
              <code class="text-xs text-muted">{{ runner.command }}</code>
            </div>
            <span class="text-xs text-muted">
              {{ runner.startedAt ? `started ${formatRelative(runner.startedAt)}` : '' }}
              {{ runner.exitCode != null ? ` · exit ${runner.exitCode}` : '' }}
            </span>
          </div>
        </template>
        <pre
          ref="logEl"
          class="max-h-72 overflow-auto p-4 font-mono text-xs leading-5 text-muted"
        >{{ runner.log.join('\n') || 'Waiting for output…' }}</pre>
      </UCard>

      <UTable
        :data="runs.items"
        :columns="columns"
        :loading="runsStatus === 'pending'"
        class="shrink-0"
        :ui="{
          base: 'table-fixed border-separate border-spacing-0',
          thead: '[&>tr]:bg-elevated/50 [&>tr]:after:content-none',
          tbody: '[&>tr]:last:[&>td]:border-b-0',
          th: 'py-2 first:rounded-l-lg last:rounded-r-lg border-y border-default first:border-l last:border-r',
          td: 'border-b border-default py-2',
          separator: 'h-0'
        }"
      >
        <template #empty>
          <div class="flex flex-col items-center gap-3 py-12 text-center text-muted">
            <UIcon name="i-lucide-radar" class="size-8" />
            <p class="text-sm">
              No runs recorded yet. Start one with "Run now" or run <code>jobs run</code> from the terminal.
            </p>
          </div>
        </template>
      </UTable>

      <p class="text-xs text-muted">
        Solid orange = returned 0 results but usually returns some · solid red = the adapter raised an error.
      </p>
    </template>
  </UDashboardPanel>
</template>
