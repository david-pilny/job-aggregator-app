<script setup lang="ts">
import type { JobSourceRef } from '#shared/types/job'

const props = withDefaults(defineProps<{ sources: JobSourceRef[], max?: number }>(), { max: 3 })

/** One badge per portal (a job can have two URLs on the same portal). */
const portals = computed(() => {
  const seen = new Map<string, JobSourceRef>()
  for (const ref of props.sources) if (!seen.has(ref.source)) seen.set(ref.source, ref)
  return [...seen.values()]
})
const visible = computed(() => portals.value.slice(0, props.max))
const hidden = computed(() => portals.value.slice(props.max))
</script>

<template>
  <div class="flex items-center gap-1">
    <UTooltip v-for="ref in visible" :key="ref.source" :text="ref.source">
      <UButton
        :icon="sourceIcon(ref.source)"
        :to="ref.url"
        target="_blank"
        rel="noopener"
        color="neutral"
        variant="ghost"
        size="xs"
        square
        :aria-label="`Open on ${ref.source}`"
        @click.stop
      />
    </UTooltip>
    <UTooltip v-if="hidden.length" :text="hidden.map(h => h.source).join(', ')">
      <UBadge color="neutral" variant="soft" size="sm">
        +{{ hidden.length }}
      </UBadge>
    </UTooltip>
  </div>
</template>
