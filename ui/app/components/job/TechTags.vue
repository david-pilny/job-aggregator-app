<script setup lang="ts">
const props = withDefaults(defineProps<{ tags: string[], max?: number }>(), { max: 4 })

const visible = computed(() => props.tags.slice(0, props.max))
const hidden = computed(() => props.tags.slice(props.max))
</script>

<template>
  <div class="flex flex-wrap items-center gap-1">
    <UBadge
      v-for="tag in visible"
      :key="tag"
      color="neutral"
      variant="outline"
      size="sm"
      class="font-mono"
    >
      {{ tag }}
    </UBadge>
    <UTooltip v-if="hidden.length" :text="hidden.join(', ')">
      <UBadge color="neutral" variant="soft" size="sm">
        +{{ hidden.length }}
      </UBadge>
    </UTooltip>
  </div>
</template>
