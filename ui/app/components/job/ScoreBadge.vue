<script setup lang="ts">
const props = defineProps<{ score: number | null }>()

const label = computed(() => props.score == null ? '–' : Math.round(props.score).toString())
</script>

<template>
  <UBadge :color="scoreColor(score)" variant="subtle" class="w-10 justify-center font-mono tabular-nums">
    {{ label }}
  </UBadge>
</template>
