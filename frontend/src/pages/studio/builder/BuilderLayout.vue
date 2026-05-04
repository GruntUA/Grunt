<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBuilderStore } from '@/stores/builder'
import { useSidebarStore } from '@/stores/sidebar'
import { grunt } from '@/core/grunt'
import { Loader2, FileJson, PanelLeft } from '@lucide/vue'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'
import SettingsTab from './tabs/SettingsTab.vue'
import PermissionsTab from './tabs/PermissionsTab.vue'
import WorkflowTab from './tabs/WorkflowTab.vue'
import ViewsTab from './tabs/ViewsTab.vue'

const props = defineProps<{ doctype: string; workspaceName?: string }>()
const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const builder = useBuilderStore()
const sidebarStore = useSidebarStore()

const backWorkspace = props.workspaceName ?? (route.params.workspaceName as string | undefined) ?? 'grunt'

const breadcrumb = computed(() => [
  { label: backWorkspace, url: `/${backWorkspace}` },
  { label: 'DocTypes', url: `/${backWorkspace}/DocType` },
  { label: builder.doctype?.label ?? props.doctype },
])

onMounted(() => builder.loadDocType(props.doctype))

// Badge: show actual path after save, or expected path before save.
// is_system doctypes are not exported to files — show a note instead.
const jsonBadge = computed(() => {
  const dt = builder.doctype
  if (!dt?.name || !dt?.module) return null

  if (builder.exportedTo) {
    const short = builder.exportedTo.split('/').slice(-3).join('/')
    return { label: short, tooltip: builder.exportedTo, variant: 'ok' as const }
  }


  const short = `${dt.module}/doctypes/${dt.name}/${dt.name}.json`
  return { label: short, tooltip: t('Expected path (save to confirm)'), variant: 'pending' as const }
})

async function handleSave() {
  try {
    const saved = await builder.save()
    if (!saved) return
    grunt.show_alert(t('DocType {label} saved', { label: saved.label || saved.name }), 'success')
    if (props.doctype === 'new') {
      router.replace(`/${backWorkspace}/DocType/${saved.name}`)
    }
  } catch (err: unknown) {
    type AxiosLike = { response?: { data?: { error?: { message?: string } } }; message?: string }
    const e = err as AxiosLike
    const msg = e.response?.data?.error?.message ?? e.message ?? t('Save error')
    grunt.show_alert(msg, 'error')
  }
}
</script>

<template>
  <div class="flex flex-col h-screen overflow-hidden">
    <Tabs v-model:value="builder.activeTab" class="flex-1 flex flex-col overflow-hidden">
      <div class="flex items-center gap-2 px-4 py-1 border-b bg-card">
        <button
          class="md:hidden size-8 flex items-center justify-center rounded-lg text-muted-foreground/80 hover:text-foreground hover:bg-muted/50 transition-colors shrink-0 -ml-2"
          @click="sidebarStore.toggleMobile"
        >
          <PanelLeft class="size-4" />
        </button>
        <Breadcrumb :model="breadcrumb" class="bg-transparent p-0">
          <template #item="{ item }">
            <template v-if="item.url">
              <router-link :to="item.url" class="text-xs font-medium text-muted-foreground/80 hover:text-foreground no-underline transition-colors">
                {{ item.label }}
              </router-link>
            </template>
            <template v-else>
              <span class="text-xs font-bold text-foreground opacity-90 truncate max-w-[300px]">{{ item.label }}</span>
            </template>
          </template>
          <template #separator>
            <span class="text-muted-foreground/40 mx-1 text-xs">/</span>
          </template>
        </Breadcrumb>
        <div class="ml-auto flex items-center gap-2">
          <div v-if="jsonBadge"
            v-tooltip.bottom="jsonBadge.tooltip"
            class="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-mono cursor-default"
            :class="{
              'border-border bg-muted text-foreground': jsonBadge.variant === 'ok',
              'border-border bg-muted text-muted-foreground': jsonBadge.variant === 'pending',
            }"
          >
            <FileJson
              class="size-3.5 shrink-0"
              :class="{
                'text-blue-500': jsonBadge.variant === 'ok',
                'text-muted-foreground': jsonBadge.variant !== 'ok',
              }"
            />
            {{ jsonBadge.label }}
          </div>
          <Button size="small" :disabled="builder.isSaving || !builder.isDirty" @click="handleSave()">
            <Loader2 v-if="builder.isSaving" class="size-4 animate-spin" />
            {{ t('Save') }}
          </Button>
        </div>
      </div>

      <div class="bg-card border-b px-2">
        <TabList class="h-auto">
          <Tab value="form" class="px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
            {{ t('Form') }}
          </Tab>
          <Tab value="settings" class="px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
            {{ t('Settings') }}
          </Tab>
          <Tab value="permissions" class="px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
            {{ t('Permissions') }}
          </Tab>
          <Tab value="workflow" class="px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
            Workflow
          </Tab>
          <Tab value="views" class="px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
            {{ t('Views') }}
          </Tab>
        </TabList>
      </div>

      <TabPanels class="flex-1 overflow-hidden flex flex-col p-0">
        <!-- Form tab: 3-column layout -->
        <TabPanel value="form" class="flex-1 overflow-hidden">
          <div class="flex h-full overflow-hidden">
            <div class="w-60 shrink-0 border-r bg-card/50">
              <FieldPalette />
            </div>
            <div class="flex-1 overflow-hidden bg-muted/20">
              <BuilderCanvas />
            </div>
            <div class="w-72 shrink-0 border-l bg-card/50">
              <PropertiesPanel />
            </div>
          </div>
        </TabPanel>

        <TabPanel value="settings">
          <SettingsTab />
        </TabPanel>

        <TabPanel value="permissions">
          <PermissionsTab />
        </TabPanel>

        <TabPanel value="workflow">
          <WorkflowTab />
        </TabPanel>

        <TabPanel value="views">
          <ViewsTab />
        </TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>
