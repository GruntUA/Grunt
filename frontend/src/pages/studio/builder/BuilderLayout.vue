<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBuilderStore } from '@/stores/builder'
import { grunt } from '@/core/grunt'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Loader2, ArrowLeft, FileJson } from 'lucide-vue-next'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
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

const backWorkspace = props.workspaceName ?? (route.params.workspaceName as string | undefined) ?? 'grunt'

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

  if (dt.is_system) {
    return { label: t('System DocType'), tooltip: t('File is not updated — built-in doctype'), variant: 'system' as const }
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
      router.replace(`/${backWorkspace}/list/DocType/${saved.name}`)
    }
  } catch (err: unknown) {
    const msg = (err as { message?: string })?.message ?? t('Save error')
    grunt.show_alert(msg, 'error')
  }
}
</script>

<template>
  <div class="flex flex-col h-screen overflow-hidden">
    <!-- Header -->
    <div class="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-card shrink-0">
      <button
        type="button"
        class="text-sm text-muted-foreground hover:text-primary transition-colors flex items-center gap-1"
        @click="router.push(`/${backWorkspace}/list/DocType`)"
      >
        <ArrowLeft class="size-4" />
        DocTypes
      </button>
      <div class="w-px h-4 bg-border" />
      <span class="text-sm font-semibold text-foreground">
        {{ builder.doctype?.label ?? props.doctype }}
        <span v-if="builder.isDirty" class="text-muted-foreground font-normal ml-1">&bull;</span>
      </span>
      <div class="ml-auto flex items-center gap-2">
        <TooltipProvider v-if="jsonBadge">
          <Tooltip>
            <TooltipTrigger as-child>
              <div
                class="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-mono cursor-default"
                :class="{
                  'border-border bg-muted text-foreground': jsonBadge.variant === 'ok',
                  'border-border bg-muted text-muted-foreground': jsonBadge.variant === 'pending',
                  'border-border bg-muted text-muted-foreground italic': jsonBadge.variant === 'system',
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
            <TooltipContent side="bottom">
              <p class="font-mono text-xs">{{ jsonBadge.tooltip }}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Button size="sm" :disabled="builder.isSaving || !builder.isDirty" @click="handleSave()">
          <Loader2 v-if="builder.isSaving" class="size-4 animate-spin" />
          {{ t('Save') }}
        </Button>
      </div>
    </div>

    <!-- Tabs -->
    <Tabs v-model="builder.activeTab" class="flex-1 flex flex-col overflow-hidden">
      <div class="border-b border-border bg-muted/30 px-4 shrink-0">
        <TabsList class="bg-transparent h-auto gap-0 p-0">
          <TabsTrigger value="form" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            {{ t('Form') }}
          </TabsTrigger>
          <TabsTrigger value="settings" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            {{ t('Settings') }}
          </TabsTrigger>
          <TabsTrigger value="permissions" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            {{ t('Permissions') }}
          </TabsTrigger>
          <TabsTrigger value="workflow" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            Workflow
          </TabsTrigger>
          <TabsTrigger value="views" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            {{ t('Views') }}
          </TabsTrigger>
        </TabsList>
      </div>

      <!-- Form tab: 3-column layout -->
      <TabsContent value="form" class="flex-1 overflow-hidden m-0 p-0">
        <div class="flex h-full overflow-hidden">
          <div class="w-60 shrink-0">
            <FieldPalette />
          </div>
          <div class="flex-1 overflow-hidden bg-muted/20">
            <BuilderCanvas />
          </div>
          <div class="w-72 shrink-0">
            <PropertiesPanel />
          </div>
        </div>
      </TabsContent>

      <!-- Settings tab -->
      <TabsContent value="settings" class="flex-1 overflow-hidden m-0 p-0">
        <SettingsTab />
      </TabsContent>

      <!-- Permissions tab -->
      <TabsContent value="permissions" class="flex-1 overflow-hidden m-0 p-0">
        <PermissionsTab />
      </TabsContent>

      <!-- Workflow tab -->
      <TabsContent value="workflow" class="flex-1 overflow-hidden m-0 p-0">
        <WorkflowTab />
      </TabsContent>

      <!-- Views tab -->
      <TabsContent value="views" class="flex-1 overflow-hidden m-0 p-0">
        <ViewsTab />
      </TabsContent>
    </Tabs>
  </div>
</template>
