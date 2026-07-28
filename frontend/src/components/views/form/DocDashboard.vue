<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { Plus } from '@lucide/vue'
import type { DocType } from '@/types'

const props = defineProps<{
  dt: DocType
  document: any
  workspace?: string
}>()

const emit = defineEmits<{
  'create-new': [doctype: string, preset: Record<string, unknown>, fieldname: string]
}>()

const dashboardFields = computed(() => {
  return props.dt.fields.filter(f => f.show_in_dashboard)
})

function getCurrentDocLinkValue(): string {
  // Tree doctypes: TreeSelect stores node.id (UUID) as the Link value.
  // Non-tree doctypes: link search stores item.name as the Link value.
  const value = props.dt.is_tree
    ? props.document?.id
    : (props.document?.name ?? props.document?.id)
  return value ? String(value) : ''
}

function getViewListTo(field: any) {
  const currentDoc = getCurrentDocLinkValue()
  if (!currentDoc || !field.dashboard_doctype) return null
  const linkField = field.dashboard_link_field || props.dt.name.toLowerCase()
  return {
    name: 'workspace-list',
    params: { workspaceName: props.workspace || 'grunt', doctype: field.dashboard_doctype },
    query: { [`filter[${linkField}__eq]`]: currentDoc },
  }
}

function handleAdd(field: any) {
  if (field.dashboard_doctype) {
    const currentDoc = getCurrentDocLinkValue()
    if (!currentDoc) return
    const linkField = field.dashboard_link_field || props.dt.name.toLowerCase()
    const preset = { [linkField]: currentDoc }
    emit('create-new', field.dashboard_doctype, preset, '')
  }
}
</script>

<template>
  <div v-if="dashboardFields.length > 0" class="flex flex-wrap gap-2 mb-1">
    <div v-for="f in dashboardFields" :key="f.fieldname"
      class="inline-flex items-center gap-2.5 bg-background border border-border/80 hover:border-primary/30 rounded-lg px-3 py-1.5 transition-colors group">

      <RouterLink
        v-if="getViewListTo(f)"
        :to="getViewListTo(f)!"
        class="flex items-center gap-2.5 no-underline"
        :title="`Переглянути ${f.label}`"
      >
        <span class="text-xs font-semibold text-muted-foreground uppercase tracking-wider group-hover:text-primary transition-colors">
          {{ f.label }}
        </span>
        <Badge variant="secondary" class="rounded-md font-mono text-xs h-4.5 px-1.5 min-w-[20px] flex items-center justify-center bg-muted/50 group-hover:bg-primary/10 group-hover:text-primary border-none transition-colors">
          {{ document[f.fieldname] || 0 }}
        </Badge>
      </RouterLink>

      <div v-else class="flex items-center gap-2.5">
        <span class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          {{ f.label }}
        </span>
        <Badge variant="secondary" class="rounded-md font-mono text-xs h-4.5 px-1.5 min-w-[20px] flex items-center justify-center bg-muted/50 border-none">
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
