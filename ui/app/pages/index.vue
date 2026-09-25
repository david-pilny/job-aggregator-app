<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { Row, SortingState } from '@tanstack/table-core'
import { useDebounceFn } from '@vueuse/core'
import { JOB_STATUSES, REMOTE_TYPES, type JobListItem, type JobStatus } from '#shared/types/job'
import type { JobSort } from '#shared/utils/jobs-query'

useDashboard()
useSeoMeta({ title: 'Jobs' })

const UButton = resolveComponent('UButton')
const UCheckbox = resolveComponent('UCheckbox')
const UBadge = resolveComponent('UBadge')
const UTooltip = resolveComponent('UTooltip')
const JobScoreBadge = resolveComponent('JobScoreBadge')
const JobTechTags = resolveComponent('JobTechTags')
const JobSourceBadges = resolveComponent('JobSourceBadges')
const JobStatusBadge = resolveComponent('JobStatusBadge')

const { query, data, status, update, reset } = useJobs()
const { data: facets } = useJobsFacets()
const { patch, setStatusMany } = useJobState()

// --- filters (URL is the source of truth; text inputs are debounced) -------------

const search = ref(query.value.q)
const minScore = ref(query.value.minScore)
watch(() => query.value.q, v => search.value = v)
watch(() => query.value.minScore, v => minScore.value = v)
const applySearch = useDebounceFn(() => update({ q: search.value }), 300)
const applyMinScore = useDebounceFn(() => update({ minScore: minScore.value }), 300)

const remoteItems = REMOTE_TYPES.map(value => ({ label: REMOTE_LABELS[value], value }))
const statusItems = JOB_STATUSES.map(value => ({ label: STATUS_LABELS[value], value }))
const sourceItems = computed(() => facets.value.sources.map(s => ({ label: `${sourceLabel(s.source)} (${s.count})`, value: s.source })))
const tagItems = computed(() => facets.value.tags.map(t => ({ label: `${t.tag} (${t.count})`, value: t.tag })))
const daysItems = [
  { label: 'Any time', value: 0 },
  { label: 'Last 3 days', value: 3 },
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 14 days', value: 14 },
  { label: 'Last 30 days', value: 30 }
]

const hasFilters = computed(() => {
  const q = query.value
  return !!(q.q || q.minScore || q.remote.length || q.source.length || q.tags.length || q.status.length || q.days || q.stale)
})

// --- sorting: TanStack state mirrors ?sort=&dir= ---------------------------------

const sorting = computed<SortingState>({
  get: () => [{ id: query.value.sort, desc: query.value.dir === 'desc' }],
  set: (state) => {
    const first = state[0]
    update({ sort: (first?.id as JobSort) ?? 'score', dir: first?.desc ? 'desc' : 'asc' })
  }
})

function sortableHeader(label: string) {
  return ({ column }: { column: { getIsSorted: () => false | 'asc' | 'desc', toggleSorting: (desc: boolean) => void } }) => {
    const sorted = column.getIsSorted()
    return h(UButton, {
      color: 'neutral',
      variant: 'ghost',
      label,
      icon: sorted ? (sorted === 'asc' ? 'i-lucide-arrow-up-narrow-wide' : 'i-lucide-arrow-down-wide-narrow') : 'i-lucide-arrow-up-down',
      class: '-mx-2.5',
      onClick: () => column.toggleSorting(sorted !== 'desc')
    })
  }
}

// --- detail slideover ------------------------------------------------------------

const selected = ref<JobListItem | null>(null)
const detailOpen = ref(false)

function openDetail(job: JobListItem) {
  selected.value = job
  detailOpen.value = true
  // Opening a fresh listing is the natural "I have looked at this" signal.
  if (job.status === 'new') patch(job, { status: 'seen' }, { silent: true })
}

function onRowSelect(_event: Event, row: Row<JobListItem>) {
  openDetail(row.original)
}

// --- keyboard navigation ----------------------------------------------------------
// A highlighted row (independent of checkbox selection) that j/k move through;
// s / x / o / Enter act on it. Shortcuts are ignored while typing in inputs.

const activeIndex = ref(-1)
watch(() => data.value.items, () => activeIndex.value = -1)

const activeJob = computed(() => data.value.items[activeIndex.value] ?? null)

function moveActive(delta: number) {
  const count = data.value.items.length
  if (!count) return
  activeIndex.value = Math.min(count - 1, Math.max(0, activeIndex.value + delta))
  document.querySelector(`[data-job-row="${activeJob.value?.id}"]`)?.scrollIntoView({ block: 'nearest' })
}

defineShortcuts({
  j: () => moveActive(1),
  k: () => moveActive(-1),
  enter: () => activeJob.value && openDetail(activeJob.value),
  s: () => activeJob.value && toggleSaved(activeJob.value),
  x: () => activeJob.value && dismiss(activeJob.value),
  o: () => {
    const url = activeJob.value?.sources[0]?.url
    if (url) window.open(url, '_blank', 'noopener')
  },
  escape: () => {
    activeIndex.value = -1
    rowSelection.value = {}
  }
})

// --- selection + actions --------------------------------------------------------

const rowSelection = ref<Record<string, boolean>>({})
watch(() => data.value.items, () => rowSelection.value = {})

const selectedJobs = computed(() =>
  data.value.items.filter(job => rowSelection.value[job.id])
)

async function bulk(status: JobStatus) {
  await setStatusMany(selectedJobs.value, status)
  rowSelection.value = {}
}

function toggleSaved(job: JobListItem) {
  return patch(job, { status: job.status === 'saved' ? 'seen' : 'saved' })
}

function dismiss(job: JobListItem) {
  return patch(job, { status: job.status === 'not_interested' ? 'seen' : 'not_interested' })
}

const columns: TableColumn<JobListItem>[] = [
  {
    id: 'select',
    header: ({ table }) => h(UCheckbox, {
      'modelValue': table.getIsSomePageRowsSelected() ? 'indeterminate' : table.getIsAllPageRowsSelected(),
      'onUpdate:modelValue': (value: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!value),
      'ariaLabel': 'Select all'
    }),
    cell: ({ row }) => h(UCheckbox, {
      'modelValue': row.getIsSelected(),
      'onUpdate:modelValue': (value: boolean | 'indeterminate') => row.toggleSelected(!!value),
      'ariaLabel': 'Select row',
      'onClick': (e: Event) => e.stopPropagation()
    }),
    enableSorting: false,
    enableHiding: false
  },
  {
    id: 'score',
    accessorKey: 'score',
    header: sortableHeader('Score'),
    cell: ({ row }) => h('span', { 'data-job-row': row.original.id }, h(JobScoreBadge, { score: row.original.score }))
  },
  {
    accessorKey: 'title',
    header: 'Title',
    enableSorting: false,
    cell: ({ row }) => h('div', { class: 'min-w-0' }, [
      h('p', { class: 'truncate font-medium text-highlighted', title: row.original.title }, row.original.title),
      h('p', { class: 'truncate text-xs text-muted' }, row.original.company)
    ])
  },
  {
    accessorKey: 'location',
    header: 'Location',
    enableSorting: false,
    cell: ({ row }) => h('span', { class: 'truncate block max-w-40', title: row.original.location ?? '' }, row.original.location ?? '')
  },
  {
    accessorKey: 'remoteType',
    header: 'Remote',
    enableSorting: false,
    cell: ({ row }) => h(UBadge, {
      color: REMOTE_COLORS[row.original.remoteType],
      variant: 'subtle',
      size: 'sm'
    }, () => REMOTE_LABELS[row.original.remoteType])
  },
  {
    id: 'salary',
    accessorFn: row => row.salaryMax ?? row.salaryMin,
    header: sortableHeader('Salary'),
    cell: ({ row }) => h('span', { class: 'whitespace-nowrap tabular-nums' }, formatSalary(row.original))
  },
  {
    accessorKey: 'techTags',
    header: 'Tags',
    enableSorting: false,
    cell: ({ row }) => h(JobTechTags, { tags: row.original.techTags })
  },
  {
    accessorKey: 'sources',
    header: 'Sources',
    enableSorting: false,
    cell: ({ row }) => h(JobSourceBadges, { sources: row.original.sources })
  },
  {
    id: 'posted',
    accessorFn: row => row.postedAt ?? row.firstSeenAt,
    header: sortableHeader('Posted'),
    cell: ({ row }) => h(UTooltip, {
      text: row.original.postedAt ? `Posted ${row.original.postedAt}` : `No date from the board; first seen ${formatDate(row.original.firstSeenAt)}`
    }, () => h('span', { class: 'whitespace-nowrap text-muted' }, [
      formatRelative(row.original.postedAt ?? row.original.firstSeenAt),
      row.original.postedAt ? '' : ' *'
    ]))
  },
  {
    accessorKey: 'status',
    header: 'Status',
    enableSorting: false,
    cell: ({ row }) => h(JobStatusBadge, { status: row.original.status })
  },
  {
    id: 'actions',
    enableSorting: false,
    enableHiding: false,
    cell: ({ row }) => h('div', { class: 'flex justify-end gap-0.5' }, [
      h(UTooltip, { text: row.original.status === 'saved' ? 'Unsave' : 'Save' }, () => h(UButton, {
        icon: row.original.status === 'saved' ? 'i-lucide-bookmark-check' : 'i-lucide-bookmark',
        color: row.original.status === 'saved' ? 'primary' : 'neutral',
        variant: 'ghost',
        size: 'sm',
        square: true,
        onClick: (e: Event) => {
          e.stopPropagation()
          toggleSaved(row.original)
        }
      })),
      h(UTooltip, { text: 'Not interested' }, () => h(UButton, {
        icon: 'i-lucide-x',
        color: row.original.status === 'not_interested' ? 'error' : 'neutral',
        variant: 'ghost',
        size: 'sm',
        square: true,
        onClick: (e: Event) => {
          e.stopPropagation()
          dismiss(row.original)
        }
      })),
      h(UTooltip, { text: 'Open listing' }, () => h(UButton, {
        icon: 'i-lucide-external-link',
        color: 'neutral',
        variant: 'ghost',
        size: 'sm',
        square: true,
        to: row.original.sources[0]?.url,
        target: '_blank',
        rel: 'noopener',
        onClick: (e: Event) => e.stopPropagation()
      }))
    ])
  }
]

function rowClass(row: { original: JobListItem }): string {
  const dimmed = row.original.status === 'not_interested' || row.original.status === 'rejected'
  const active = row.original.id === activeJob.value?.id
  return [dimmed ? 'opacity-50' : '', active ? 'bg-primary/10 ring-1 ring-inset ring-primary/40' : ''].join(' ')
}

const rangeLabel = computed(() => {
  const { total, page, pageSize } = data.value
  if (!total) return 'No jobs'
  const from = (page - 1) * pageSize + 1
  return `${from}–${Math.min(page * pageSize, total)} of ${total}`
})
</script>

<template>
  <UDashboardPanel id="jobs">
    <template #header>
      <UDashboardNavbar title="Jobs" :ui="{ right: 'gap-3' }">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <span class="text-sm text-muted tabular-nums">{{ rangeLabel }}</span>
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar>
        <div class="flex w-full flex-wrap items-center gap-2 py-1">
          <UInput
            v-model="search"
            icon="i-lucide-search"
            placeholder="Search title, company, description…"
            class="w-64"
            @update:model-value="applySearch"
          />

          <div class="flex w-44 items-center gap-2 px-1">
            <span class="text-xs text-muted whitespace-nowrap">Score ≥ {{ minScore }}</span>
            <USlider
              v-model="minScore"
              :min="0"
              :max="100"
              :step="5"
              size="xs"
              @update:model-value="applyMinScore"
            />
          </div>

          <USelectMenu
            :model-value="query.remote"
            :items="remoteItems"
            value-key="value"
            multiple
            :search-input="false"
            placeholder="Remote"
            class="w-32"
            @update:model-value="(v: string[]) => update({ remote: v as typeof query.remote })"
          />
          <USelectMenu
            :model-value="query.source"
            :items="sourceItems"
            value-key="value"
            multiple
            placeholder="Source"
            class="w-40"
            @update:model-value="(v: string[]) => update({ source: v })"
          />
          <USelectMenu
            :model-value="query.tags"
            :items="tagItems"
            value-key="value"
            multiple
            placeholder="Tags"
            class="w-40"
            @update:model-value="(v: string[]) => update({ tags: v })"
          />
          <USelectMenu
            :model-value="query.status"
            :items="statusItems"
            value-key="value"
            multiple
            :search-input="false"
            placeholder="Status"
            class="w-36"
            @update:model-value="(v: string[]) => update({ status: v as typeof query.status })"
          />
          <USelect
            :model-value="query.days"
            :items="daysItems"
            class="w-32"
            @update:model-value="(v: number) => update({ days: v })"
          />
          <UCheckbox
            :model-value="query.stale"
            label="Include stale"
            size="sm"
            @update:model-value="(v: boolean | 'indeterminate') => update({ stale: !!v })"
          />

          <UButton
            v-if="hasFilters"
            label="Reset"
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            size="sm"
            @click="reset"
          />

          <div v-if="selectedJobs.length" class="ml-auto flex items-center gap-1.5">
            <UKbd>{{ selectedJobs.length }}</UKbd>
            <UButton
              label="Mark seen"
              icon="i-lucide-eye"
              color="neutral"
              variant="subtle"
              size="sm"
              @click="bulk('seen')"
            />
            <UButton
              label="Not interested"
              icon="i-lucide-x"
              color="error"
              variant="subtle"
              size="sm"
              @click="bulk('not_interested')"
            />
          </div>
        </div>
      </UDashboardToolbar>
    </template>

    <template #body>
      <JobDetailSlideover v-model:open="detailOpen" :job="selected" />

      <UTable
        v-model:sorting="sorting"
        v-model:row-selection="rowSelection"
        :sorting-options="{ manualSorting: true }"
        :get-row-id="(row: JobListItem) => row.id"
        :data="data.items"
        :columns="columns"
        :loading="status === 'pending'"
        sticky
        class="shrink-0"
        :meta="{ class: { tr: rowClass } }"
        :ui="{
          base: 'table-fixed border-separate border-spacing-0',
          thead: '[&>tr]:bg-elevated/50 [&>tr]:after:content-none',
          tbody: '[&>tr]:last:[&>td]:border-b-0',
          th: 'py-2 first:rounded-l-lg last:rounded-r-lg border-y border-default first:border-l last:border-r',
          td: 'border-b border-default py-2',
          tr: 'cursor-pointer',
          separator: 'h-0'
        }"
        @select="onRowSelect"
      >
        <template #empty>
          <div class="flex flex-col items-center gap-3 py-12 text-center">
            <UIcon name="i-lucide-search-x" class="size-8 text-muted" />
            <p class="text-sm text-muted">
              No jobs match these filters.
            </p>
            <UButton
              v-if="hasFilters"
              label="Reset filters"
              color="neutral"
              variant="outline"
              size="sm"
              @click="reset"
            />
          </div>
        </template>
      </UTable>

      <div class="mt-auto flex items-center justify-between gap-3 border-t border-default pt-4">
        <div class="flex items-center gap-2 text-xs text-muted">
          <span v-if="selectedJobs.length">{{ selectedJobs.length }} selected ·</span>
          <span>* date from first sighting, the board gives none</span>
          <span class="hidden items-center gap-1 lg:inline-flex">
            · <UKbd>j</UKbd><UKbd>k</UKbd> move <UKbd>↵</UKbd> open <UKbd>s</UKbd> save <UKbd>x</UKbd> dismiss <UKbd>o</UKbd> listing
          </span>
        </div>
        <div class="flex items-center gap-3">
          <USelect
            :model-value="query.pageSize"
            :items="[25, 50, 100, 200].map(n => ({ label: `${n} / page`, value: n }))"
            size="sm"
            class="w-28"
            @update:model-value="(v: number) => update({ pageSize: v })"
          />
          <UPagination
            :page="query.page"
            :items-per-page="query.pageSize"
            :total="data.total"
            :sibling-count="1"
            size="sm"
            @update:page="(p: number) => update({ page: p })"
          />
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
