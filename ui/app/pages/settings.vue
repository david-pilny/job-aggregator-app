<script setup lang="ts">
useDashboard()
useSeoMeta({ title: 'Settings' })
</script>

<template>
  <UDashboardPanel id="settings">
    <template #header>
      <UDashboardNavbar title="Settings">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="flex flex-col items-center gap-3 py-24 text-center text-muted">
        <UIcon name="i-lucide-settings" class="size-8" />
        <p class="text-sm">
          The config.yaml viewer arrives in build step 6.
        </p>
      </div>
    </template>
  </UDashboardPanel>
</template>
