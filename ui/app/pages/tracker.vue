<script setup lang="ts">
import type { JobListItem } from '#shared/types/job'
import type { TrackerStage } from '#shared/utils/tracker'

useDashboard()
useSeoMeta({ title: 'Tracker' })

const { data, status, columns, move } = useTracker()

const selected = ref<JobListItem | null>(null)
const detailOpen = ref(false)

function open(job: JobListItem) {
  selected.value = job
  detailOpen.value = true
}

// --- native drag & drop (no library: one id travels in dataTransfer) ----------------

const dragOver = ref<TrackerStage | null>(null)

function onDrop(event: DragEvent, stage: TrackerStage) {
  dragOver.value = null
  const id = event.dataTransfer?.getData('text/job-id')
  const job = data.value.items.find(j => j.id === id)
  if (job) move(job, stage)
}

const total = computed(() => data.value.items.length)

// Static class strings so Tailwind keeps them in the build.
const STAGE_TEXT: Record<TrackerStage, string> = {
  saved: 'text-info',
  applied: 'text-primary',
  interviewing: 'text-warning',
  offer: 'text-success',
  rejected: 'text-error'
}
</script>

<template>
  <UDashboardPanel id="tracker">
    <template #header>
      <UDashboardNavbar title="Tracker">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <span class="text-sm text-muted tabular-nums">{{ total }} tracked</span>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <JobDetailSlideover v-model:open="detailOpen" :job="selected" />

      <div v-if="status === 'pending' && !total" class="grid gap-4 md:grid-cols-5">
        <USkeleton v-for="n in 5" :key="n" class="h-64" />
      </div>

      <div
        v-else-if="!total"
        class="flex flex-col items-center gap-3 py-24 text-center text-muted"
      >
        <UIcon name="i-lucide-kanban" class="size-8" />
        <p class="text-sm">
          Nothing tracked yet. Save a job from the list to start a pipeline.
        </p>
        <UButton
          label="Browse jobs"
          to="/"
          color="neutral"
          variant="outline"
          size="sm"
        />
      </div>

      <div v-else class="grid gap-4 md:grid-cols-5">
        <section
          v-for="column in columns"
          :key="column.stage"
          class="flex min-h-64 flex-col rounded-lg border p-2 transition"
          :class="dragOver === column.stage ? 'border-primary bg-primary/5' : 'border-default bg-elevated/25'"
          @dragover.prevent="dragOver = column.stage"
          @dragleave="dragOver === column.stage && (dragOver = null)"
          @drop.prevent="onDrop($event, column.stage)"
        >
          <header class="mb-2 flex items-center justify-between px-1">
            <span class="inline-flex items-center gap-1.5 text-sm font-medium">
              <UIcon :name="STAGE_ICONS[column.stage]" class="size-4" :class="STAGE_TEXT[column.stage]" />
              {{ STATUS_LABELS[column.stage] }}
            </span>
            <UBadge color="neutral" variant="subtle" size="sm">
              {{ column.items.length }}
            </UBadge>
          </header>

          <div class="flex flex-1 flex-col gap-2">
            <TrackerCard
              v-for="job in column.items"
              :key="job.id"
              :job="job"
              @open="open(job)"
              @move="move(job, $event)"
            />
            <p v-if="!column.items.length" class="py-6 text-center text-xs text-muted">
              Drop here
            </p>
          </div>
        </section>
      </div>
    </template>
  </UDashboardPanel>
</template>
