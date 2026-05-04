<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from '@lucide/vue'
import type { DocType } from '@/types'

const props = defineProps<{
  dt: DocType
  document: any
}>()

const emit = defineEmits<{
  'create-new': [doctype: string, preset: Record<string, unknown>, fieldname: string]
  'view-list': [doctype: string, filters: Record<string, unknown>]
}>()

const dashboardFields = computed(() => {
  return props.dt.fields.filter(f => f.show_in_dashboard)
})

function getCurrentDocLinkValue(): string {
  // Link fields store document name (human-readable/autoname), not internal id.
  const value = props.document?.name ?? props.document?.id
  return value ? String(value) : ''
}

function handleAdd(field: any) {
  if (field.dashboard_doctype) {
    const currentDoc = getCurrentDocLinkValue()
    if (!currentDoc) return
    // If dashboard_link_field is set, use it. Otherwise fallback to lowercase parent doctype name.
    const linkField = field.dashboard_link_field || props.dt.name.toLowerCase()
    const preset = { [linkField]: currentDoc }
    emit('create-new', field.dashboard_doctype, preset, '')
  }
}

function handleViewList(field: any) {
  if (field.dashboard_doctype) {
    const currentDoc = getCurrentDocLinkValue()
    if (!currentDoc) return
    const linkField = field.dashboard_link_field || props.dt.name.toLowerCase()
    const filters = { [linkField]: currentDoc }
    emit('view-list', field.dashboard_doctype, filters)
  }
}
</script>

<template>
  <div v-if="dashboardFields.length > 0" class="flex flex-wrap gap-2 mb-1">
    <div v-for="f in dashboardFields" :key="f.fieldname" 
      class="inline-flex items-center gap-2.5 bg-background border border-border/80 hover:border-primary/30 rounded-lg px-3 py-1.5 shadow-sm transition-all group">
      
      <div 
        class="flex items-center gap-2.5 cursor-pointer"
        @click="handleViewList(f)"
        :title="`Переглянути ${f.label}`"
      >
        <span class="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider group-hover:text-primary transition-colors">
          {{ f.label }}
        </span>
        <Badge severity="secondary" class="rounded-md font-mono text-[10px] h-4.5 px-1.5 min-w-[20px] flex items-center justify-center bg-muted/50 group-hover:bg-primary/10 group-hover:text-primary border-none transition-colors">
          {{ document[f.fieldname] || 0 }}
        </Badge>
      </div>

      <button 
        v-if="f.dashboard_doctype"
        type="button"
        class="size-5 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary flex items-center justify-center transition-colors border border-transparent hover:border-primary/20 -mr-1"
        @click="handleAdd(f)"
        :title="`Створити новий ${f.dashboard_doctype}`"
      >
        <Plus class="size-3.5" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.group:hover {
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
}
</style>
