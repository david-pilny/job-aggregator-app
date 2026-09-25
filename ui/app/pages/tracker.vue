<script setup lang="ts">
useDashboard()
useSeoMeta({ title: 'Tracker' })
</script>

<template>
  <UDashboardPanel id="tracker">
    <template #header>
      <UDashboardNavbar title="Tracker">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col items-center gap-3 py-24 text-center text-muted">
        <UIcon name="i-lucide-kanban" class="size-8" />
        <p class="text-sm">
          The application tracker arrives in build step 4.
        </p>
      </div>
    </template>
  </UDashboardPanel>
</template>
