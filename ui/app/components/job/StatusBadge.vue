<script setup lang="ts">
import type { JobStatus } from '#shared/types/job'

defineProps<{ status: JobStatus }>()
</script>

<template>
  <UBadge :color="STATUS_COLORS[status]" :variant="status === 'new' ? 'outline' : 'subtle'" size="sm">
    {{ STATUS_LABELS[status] }}
  </UBadge>
</template>
