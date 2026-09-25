<script setup lang="ts">
useDashboard()
useSeoMeta({ title: 'Settings' })

interface ConfigFile {
  path: string
  content: string
  valid: boolean
  error: string | null
  modifiedAt: string
}

const { data: config, status, error, refresh } = useFetch<ConfigFile>('/api/config', {
  key: 'config',
  lazy: true
})

const toast = useToast()

async function copy() {
  if (!config.value) return
  await navigator.clipboard.writeText(config.value.content)
  toast.add({ title: 'config.yaml copied', icon: 'i-lucide-clipboard-check' })
}
</script>

<template>
  <UDashboardPanel id="settings">
    <template #header>
      <UDashboardNavbar title="Settings" :ui="{ right: 'gap-2' }">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UButton
            label="Copy"
            icon="i-lucide-clipboard"
            color="neutral"
            variant="outline"
            size="sm"
            :disabled="!config"
            @click="copy"
          />
          <UButton
            label="Reload"
            icon="i-lucide-refresh-cw"
            color="neutral"
            variant="outline"
            size="sm"
            :loading="status === 'pending'"
            @click="refresh()"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UAlert
        color="neutral"
        variant="subtle"
        icon="i-lucide-info"
        title="Read-only"
        description="The pipeline's config.yaml is shown as-is. Edit it in your editor; the next run (or 'Run now') picks the change up."
      />

      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Could not read config.yaml"
        :description="error.statusMessage ?? String(error)"
      />

      <template v-else-if="config">
        <div class="flex flex-wrap items-center gap-2 text-xs text-muted">
          <code>{{ config.path }}</code>
          <span>· modified {{ formatRelative(config.modifiedAt) }}</span>
          <UBadge
            v-if="config.valid"
            color="success"
            variant="subtle"
            size="sm"
          >
            valid YAML
          </UBadge>
          <UTooltip v-else :text="config.error ?? ''">
            <UBadge color="error" variant="subtle" size="sm">
              invalid YAML
            </UBadge>
          </UTooltip>
        </div>

        <pre class="overflow-auto rounded-lg border border-default bg-elevated/50 p-4 font-mono text-xs leading-5">{{ config.content }}</pre>
      </template>

      <div v-else class="space-y-2">
        <USkeleton class="h-4 w-1/2" />
        <USkeleton class="h-96 w-full" />
      </div>
    </template>
  </UDashboardPanel>
</template>
