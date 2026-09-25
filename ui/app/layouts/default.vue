<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const open = ref(false)

const links = [[{
  label: 'Jobs',
  icon: 'i-lucide-briefcase',
  to: '/',
  exact: true,
  onSelect: () => { open.value = false }
}, {
  label: 'Tracker',
  icon: 'i-lucide-kanban',
  to: '/tracker',
  onSelect: () => { open.value = false }
}, {
  label: 'Sources & runs',
  icon: 'i-lucide-radar',
  to: '/runs',
  onSelect: () => { open.value = false }
}, {
  label: 'Settings',
  icon: 'i-lucide-settings',
  to: '/settings',
  onSelect: () => { open.value = false }
}]] satisfies NavigationMenuItem[][]

const groups = computed(() => [{
  id: 'links',
  label: 'Go to',
  items: links.flat()
}])
</script>

<template>
  <UDashboardGroup unit="rem">
    <UDashboardSidebar
      id="default"
      v-model:open="open"
      collapsible
      resizable
      class="bg-elevated/25"
      :ui="{ footer: 'lg:border-t lg:border-default' }"
    >
      <template #header="{ collapsed }">
        <div class="flex items-center gap-2 px-1 font-semibold text-highlighted">
          <UIcon name="i-lucide-radar" class="size-5 text-primary" />
          <span v-if="!collapsed">Job aggregator</span>
        </div>
      </template>

      <template #default="{ collapsed }">
        <UDashboardSearchButton :collapsed="collapsed" class="bg-transparent ring-default" />

        <UNavigationMenu
          :collapsed="collapsed"
          :items="links[0]"
          orientation="vertical"
          tooltip
          popover
        />
      </template>

      <template #footer="{ collapsed }">
        <div class="flex w-full items-center" :class="collapsed ? 'justify-center' : 'justify-between'">
          <span v-if="!collapsed" class="text-xs text-muted">local · single user</span>
          <UColorModeButton />
        </div>
      </template>
    </UDashboardSidebar>

    <UDashboardSearch :groups="groups" />

    <slot />
  </UDashboardGroup>
</template>
