<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBuilderStore } from '@/stores/builder'
import { useSidebar } from '@/components/ui/sidebar'
import { grunt } from '@/core/grunt'
import { Loader2, FileJson, PanelLeft } from '@lucide/vue'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'
import SettingsTab from './tabs/SettingsTab.vue'
import PermissionsTab from './tabs/PermissionsTab.vue'
import WorkflowTab from './tabs/WorkflowTab.vue'
import ViewsTab from './tabs/ViewsTab.vue'
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
const props = defineProps<{ doctype: string; workspaceName?: string }>()
const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const builder = useBuilderStore()
const { toggleSidebar } = useSidebar()

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
    grunt.show_alert(`DocType «${saved.label || saved.name}» збережено`, 'success')
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
    <Tabs v-model="builder.activeTab" class="flex-1 flex flex-col overflow-hidden">
      <div class="flex items-center gap-2 px-4 py-1 border-b bg-card">
        <button
          class="md:hidden size-8 flex items-center justify-center rounded-lg text-muted-foreground/80 hover:text-foreground hover:bg-muted/50 transition-colors shrink-0 -ml-2"
          @click="toggleSidebar"
        >
          <PanelLeft class="size-4" />
        </button>
        <Breadcrumb class="bg-transparent p-0">
          <BreadcrumbList class="flex-nowrap gap-0">
            <template v-for="(item, idx) in breadcrumb" :key="idx">
              <BreadcrumbSeparator v-if="idx > 0" class="mx-1">
                <span class="text-muted-foreground/40 text-xs">/</span>
              </BreadcrumbSeparator>
              <BreadcrumbItem>
                <BreadcrumbLink v-if="item.url" as-child>
                  <router-link :to="item.url" class="text-xs font-medium text-muted-foreground/80 hover:text-foreground no-underline transition-colors">
                    {{ item.label }}
                  </router-link>
                </BreadcrumbLink>
                <span v-else class="text-xs font-semibold text-foreground opacity-90 truncate max-w-[300px]">{{ item.label }}</span>
              </BreadcrumbItem>
            </template>
          </BreadcrumbList>
        </Breadcrumb>
        <div class="ml-auto flex items-center gap-2">
          <Tooltip v-if="jsonBadge">
            <TooltipTrigger as-child>
              <div
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
            </TooltipTrigger>
            <TooltipContent side="bottom">{{ jsonBadge.tooltip }}</TooltipContent>
          </Tooltip>
          <Button size="sm" :disabled="builder.isSaving || !builder.isDirty" @click="handleSave()">
            <Loader2 v-if="builder.isSaving" class="size-4 animate-spin" />
            {{ t('Save') }}
          </Button>
        </div>
      </div>

      <div class="bg-card border-b px-2">
        <TabsList class="h-auto">
          <TabsTrigger value="form" class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider">
            {{ t('Form') }}
          </TabsTrigger>
          <TabsTrigger value="settings" class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider">
            {{ t('Settings') }}
          </TabsTrigger>
          <TabsTrigger value="permissions" class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider">
            {{ t('Permissions') }}
          </TabsTrigger>
          <TabsTrigger value="workflow" class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider">
            Workflow
          </TabsTrigger>
          <TabsTrigger value="views" class="px-4 py-2.5 text-xs font-semibold uppercase tracking-wider">
            {{ t('Views') }}
          </TabsTrigger>
        </TabsList>
      </div>

      <!-- Form tab: 3-column layout -->
      <TabsContent value="form" class="flex-1 overflow-hidden flex flex-col p-0">
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
      </TabsContent>

      <TabsContent value="settings" class="flex-1 overflow-hidden flex flex-col p-0">
        <SettingsTab />
      </TabsContent>

      <TabsContent value="permissions" class="flex-1 overflow-hidden flex flex-col p-0">
        <PermissionsTab />
      </TabsContent>

      <TabsContent value="workflow" class="flex-1 overflow-hidden flex flex-col p-0">
        <WorkflowTab />
      </TabsContent>

      <TabsContent value="views" class="flex-1 overflow-hidden flex flex-col p-0">
        <ViewsTab />
      </TabsContent>
    </Tabs>
  </div>
</template>
