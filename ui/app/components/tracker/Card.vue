<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import { JOB_STATUSES, type JobListItem, type JobStatus } from '#shared/types/job'

const props = defineProps<{ job: JobListItem }>()
const emit = defineEmits<{ move: [status: JobStatus], open: [] }>()

/** Move menu: every status except the current one, so cards work without dragging. */
const moveItems = computed<DropdownMenuItem[]>(() => [
  { type: 'label', label: 'Move to' },
  ...JOB_STATUSES.filter(s => s !== props.job.status && s !== 'new').map(status => ({
    label: STATUS_LABELS[status],
    icon: status === 'not_interested' ? 'i-lucide-x' : STAGE_ICONS[status as keyof typeof STAGE_ICONS] ?? 'i-lucide-eye',
    onSelect: () => emit('move', status)
  }))
])

function onDragStart(event: DragEvent) {
  event.dataTransfer?.setData('text/job-id', props.job.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
</script>

<template>
  <div
    draggable="true"
    class="group cursor-grab rounded-lg border border-default bg-default p-3 text-sm shadow-xs transition hover:border-accented active:cursor-grabbing"
    @dragstart="onDragStart"
    @click="emit('open')"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <p class="truncate font-medium text-highlighted" :title="job.title">
          {{ job.title }}
        </p>
        <p class="truncate text-xs text-muted">
          {{ job.company }}<span v-if="job.location"> · {{ job.location }}</span>
        </p>
      </div>
      <JobScoreBadge :score="job.score" />
    </div>

    <div class="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">
      <UBadge :color="REMOTE_COLORS[job.remoteType]" variant="subtle" size="sm">
        {{ REMOTE_LABELS[job.remoteType] }}
      </UBadge>
      <span v-if="formatSalary(job)" class="tabular-nums">{{ formatSalary(job) }}</span>
      <span v-if="job.appliedAt">applied {{ formatDate(job.appliedAt) }}</span>
    </div>

    <p v-if="job.notes" class="mt-2 line-clamp-2 text-xs text-muted" :title="job.notes">
      {{ job.notes }}
    </p>

    <div class="mt-2 flex items-center justify-end gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
      <UButton
        icon="i-lucide-external-link"
        color="neutral"
        variant="ghost"
        size="xs"
        square
        :to="job.sources[0]?.url"
        target="_blank"
        rel="noopener"
        aria-label="Open listing"
        @click.stop
      />
      <UDropdownMenu :items="moveItems" :content="{ align: 'end' }">
        <UButton
          icon="i-lucide-move-right"
          color="neutral"
          variant="ghost"
          size="xs"
          square
          aria-label="Move"
          @click.stop
        />
      </UDropdownMenu>
    </div>
  </div>
</template>
