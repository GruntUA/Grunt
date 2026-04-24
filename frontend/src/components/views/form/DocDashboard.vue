<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from '@lucide/vue'
import type { DocType } from '@/types'

const props = defineProps<{
  dt: DocType
  document: any
}>()

const emit = defineEmits<{
  'create-new': [doctype: string, preset: string, fieldname: string]
}>()

const dashboardFields = computed(() => {
  return props.dt.fields.filter(f => f.show_in_dashboard)
})

function handleAdd(field: any) {
  if (field.dashboard_doctype) {
    // We pass a preset object to pre-fill the back-link field.
    // Convention: target doctype has a field named after our doctype (lowercase).
    const targetField = props.dt.name.toLowerCase()
    const preset = { [targetField]: props.document.id }
    emit('create-new', field.dashboard_doctype, preset, '')
  }
}
</script>

<template>
  <div v-if="dashboardFields.length > 0" class="flex flex-wrap gap-2 mb-1">
    <div v-for="f in dashboardFields" :key="f.fieldname" 
      class="inline-flex items-center gap-2.5 bg-background border border-border/80 hover:border-primary/30 rounded-lg px-3 py-1.5 shadow-sm transition-all group">
      <span class="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">{{ f.label }}</span>
      <Badge severity="secondary" class="rounded-md font-mono text-[10px] h-4.5 px-1.5 min-w-[20px] flex items-center justify-center bg-muted/50 border-none">
        {{ document[f.fieldname] || 0 }}
      </Badge>
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
