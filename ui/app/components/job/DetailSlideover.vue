<script setup lang="ts">
import { useDebounceFn } from '@vueuse/core'
import { JOB_STATUSES, type JobDetail, type JobListItem, type JobStatus } from '#shared/types/job'

/**
 * Detail view for the row that is currently selected in the list. The `job`
 * prop is the list's own row object, so status/notes changes made here are
 * visible in the table immediately; only the heavy fields (description, score
 * breakdown, all URLs) are fetched on demand.
 */
const props = defineProps<{ job: JobListItem | null }>()
const open = defineModel<boolean>('open', { default: false })

const { patch } = useJobState()

const { data: detail, status: loadStatus } = useLazyAsyncData<JobDetail | null>(
  () => `job-detail-${props.job?.id ?? 'none'}`,
  () => props.job ? $fetch<JobDetail>(`/api/jobs/${props.job.id}`) : Promise.resolve(null),
  { watch: [() => props.job?.id], default: () => null }
)

// --- status -----------------------------------------------------------------------

const statusItems = JOB_STATUSES.map(value => ({
  label: STATUS_LABELS[value],
  value,
  chip: { color: STATUS_COLORS[value] }
}))

function setStatus(status: JobStatus) {
  if (props.job) patch(props.job, { status })
}

// --- notes with autosave ----------------------------------------------------------

const notes = ref('')
const notesState = ref<'idle' | 'dirty' | 'saving' | 'saved' | 'error'>('idle')

watch(() => props.job?.id, () => {
  notes.value = props.job?.notes ?? ''
  notesState.value = 'idle'
}, { immediate: true })

async function saveNotes() {
  if (!props.job || notesState.value !== 'dirty') return
  notesState.value = 'saving'
  const result = await patch(props.job, { notes: notes.value.trim() || null }, { silent: true })
  notesState.value = result ? 'saved' : 'error'
}

const saveNotesDebounced = useDebounceFn(saveNotes, 800)

function onNotesInput() {
  notesState.value = 'dirty'
  saveNotesDebounced()
}

// Closing the panel flushes a pending save instead of losing it to the debounce.
watch(open, (isOpen) => {
  if (!isOpen) saveNotes()
})

const notesHint = computed(() => ({
  idle: '',
  dirty: 'Unsaved…',
  saving: 'Saving…',
  saved: 'Saved',
  error: 'Save failed'
})[notesState.value])

// --- score breakdown ---------------------------------------------------------------

/**
 * The pipeline stores points per factor but not the weights they came from,
 * so bars are scaled by the default weights from config.yaml (falling back to
 * the points themselves for unknown factors).
 */
const DEFAULT_WEIGHTS: Record<string, number> = {
  stack: 45,
  remote: 25,
  seniority: 15,
  salary: 5,
  freshness: 10
}

const breakdown = computed(() =>
  Object.entries(detail.value?.scoreBreakdown ?? {}).map(([factor, points]) => ({
    factor,
    points,
    max: Math.max(DEFAULT_WEIGHTS[factor] ?? points, points, 1)
  }))
)

const primaryUrl = computed(() => detail.value?.primaryUrl ?? props.job?.sources[0]?.url)
</script>

<template>
  <USlideover
    v-model:open="open"
    :title="job?.title ?? ''"
    :description="job?.company"
    :ui="{ content: 'sm:max-w-2xl', body: 'space-y-6' }"
  >
    <template #body>
      <template v-if="job">
        <!-- Facts strip -->
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <JobScoreBadge :score="job.score" />
          <UBadge :color="REMOTE_COLORS[job.remoteType]" variant="subtle">
            {{ REMOTE_LABELS[job.remoteType] }}
          </UBadge>
          <span v-if="job.location" class="inline-flex items-center gap-1 text-muted">
            <UIcon name="i-lucide-map-pin" class="size-4" />{{ job.location }}
          </span>
          <span v-if="formatSalary(job)" class="inline-flex items-center gap-1 tabular-nums">
            <UIcon name="i-lucide-banknote" class="size-4 text-muted" />{{ formatSalary(job) }}
          </span>
          <span class="inline-flex items-center gap-1 text-muted">
            <UIcon name="i-lucide-calendar" class="size-4" />
            {{ job.postedAt ? `posted ${job.postedAt}` : `first seen ${formatDate(job.firstSeenAt)}` }}
          </span>
        </div>

        <!-- Status + notes -->
        <div class="grid gap-4 rounded-lg border border-default p-4 sm:grid-cols-[12rem_1fr]">
          <UFormField label="Status">
            <USelect
              :model-value="job.status"
              :items="statusItems"
              class="w-full"
              @update:model-value="setStatus"
            />
            <template #hint>
              <span v-if="job.appliedAt" class="text-xs">applied {{ formatDate(job.appliedAt) }}</span>
            </template>
          </UFormField>

          <UFormField label="Notes" :hint="notesHint">
            <UTextarea
              v-model="notes"
              autoresize
              :rows="3"
              :maxrows="10"
              placeholder="Contact, salary asked, impressions…"
              class="w-full"
              @update:model-value="onNotesInput"
            />
          </UFormField>
        </div>

        <!-- Tags + sources -->
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Tech tags
            </h3>
            <JobTechTags v-if="job.techTags.length" :tags="job.techTags" :max="100" />
            <p v-else class="text-sm text-muted">
              None detected
            </p>
          </div>
          <div>
            <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Listed on
            </h3>
            <div class="flex flex-col gap-1">
              <UButton
                v-for="ref in job.sources"
                :key="ref.url"
                :icon="sourceIcon(ref.source)"
                :label="ref.source"
                :to="ref.url"
                target="_blank"
                rel="noopener"
                color="neutral"
                variant="link"
                size="sm"
                trailing-icon="i-lucide-external-link"
                class="justify-start px-0"
              />
            </div>
          </div>
        </div>

        <!-- Score breakdown -->
        <div>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Score breakdown
          </h3>
          <div v-if="breakdown.length" class="space-y-2">
            <div v-for="item in breakdown" :key="item.factor" class="grid grid-cols-[6rem_1fr_3rem] items-center gap-3 text-sm">
              <span class="capitalize text-muted">{{ item.factor }}</span>
              <UProgress
                :model-value="item.points"
                :max="item.max"
                size="sm"
                :color="item.points < 0 ? 'error' : 'primary'"
              />
              <span class="text-right tabular-nums">{{ item.points }}</span>
            </div>
          </div>
          <USkeleton v-else-if="loadStatus === 'pending'" class="h-16 w-full" />
          <p v-else class="text-sm text-muted">
            Not scored yet
          </p>
        </div>

        <!-- Description (stored as plain text; rendered with interpolation, never v-html) -->
        <div>
          <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Description
          </h3>
          <div v-if="loadStatus === 'pending'" class="space-y-2">
            <USkeleton class="h-4 w-full" />
            <USkeleton class="h-4 w-11/12" />
            <USkeleton class="h-4 w-3/4" />
          </div>
          <p v-else-if="detail?.description" class="whitespace-pre-wrap text-sm leading-relaxed">
            {{ detail.description }}
          </p>
          <UAlert
            v-else
            color="neutral"
            variant="subtle"
            icon="i-lucide-file-question"
            title="No description from this board"
            description="LinkedIn, jobs.cz and prace.cz listings carry only the card data. Open the listing for the full text."
          />
        </div>

        <p class="text-xs text-muted">
          id {{ job.id }} · language {{ job.language }} · last seen {{ formatRelative(job.lastSeenAt) }}
        </p>
      </template>
    </template>

    <template #footer>
      <div class="flex w-full items-center justify-between gap-2">
        <UButton
          v-if="job"
          :icon="job.status === 'saved' ? 'i-lucide-bookmark-check' : 'i-lucide-bookmark'"
          :label="job.status === 'saved' ? 'Saved' : 'Save'"
          :color="job.status === 'saved' ? 'primary' : 'neutral'"
          variant="subtle"
          @click="setStatus(job.status === 'saved' ? 'seen' : 'saved')"
        />
        <div class="flex items-center gap-2">
          <UButton
            label="Close"
            color="neutral"
            variant="ghost"
            @click="open = false"
          />
          <UButton
            v-if="primaryUrl"
            label="Open listing"
            icon="i-lucide-external-link"
            :to="primaryUrl"
            target="_blank"
            rel="noopener"
          />
        </div>
      </div>
    </template>
  </USlideover>
</template>
