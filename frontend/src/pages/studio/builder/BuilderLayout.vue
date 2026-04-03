<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useBuilderStore } from '@/stores/builder'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Loader2, ArrowLeft } from 'lucide-vue-next'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'
import SettingsTab from './tabs/SettingsTab.vue'
import PermissionsTab from './tabs/PermissionsTab.vue'
import WorkflowTab from './tabs/WorkflowTab.vue'
import ViewsTab from './tabs/ViewsTab.vue'

const props = defineProps<{ doctype: string; workspaceName?: string }>()
const router = useRouter()
const route = useRoute()
const builder = useBuilderStore()

const backWorkspace = props.workspaceName ?? (route.params.workspaceName as string | undefined) ?? 'grunt'

onMounted(() => builder.loadDocType(props.doctype))

async function handleSave() {
  const saved = await builder.save()
  if (saved && props.doctype === 'new') {
    router.replace(`/${backWorkspace}/list/DocType/${saved.name}`)
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
      <div class="ml-auto">
        <Button size="sm" :disabled="builder.isSaving || !builder.isDirty" @click="handleSave()">
          <Loader2 v-if="builder.isSaving" class="size-4 animate-spin" />
          Зберегти
        </Button>
      </div>
    </div>

    <!-- Tabs -->
    <Tabs v-model="builder.activeTab" class="flex-1 flex flex-col overflow-hidden">
      <div class="border-b border-border bg-muted/30 px-4 shrink-0">
        <TabsList class="bg-transparent h-auto gap-0 p-0">
          <TabsTrigger value="form" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            Форма
          </TabsTrigger>
          <TabsTrigger value="settings" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            Налаштування
          </TabsTrigger>
          <TabsTrigger value="permissions" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            Права
          </TabsTrigger>
          <TabsTrigger value="workflow" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            Workflow
          </TabsTrigger>
          <TabsTrigger value="views" class="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2 text-sm">
            Вигляди
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
