<script setup lang="ts">
useDashboard()
useSeoMeta({ title: 'Sources & runs' })
</script>

<template>
  <UDashboardPanel id="runs">
    <template #header>
      <UDashboardNavbar title="Sources & runs">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col items-center gap-3 py-24 text-center text-muted">
        <UIcon name="i-lucide-radar" class="size-8" />
        <p class="text-sm">
          Run history and the "Run now" button arrive in build step 5.
        </p>
      </div>
    </template>
  </UDashboardPanel>
</template>
