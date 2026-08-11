<script setup lang="ts">
import { computed } from 'vue'
import { GitBranch } from '@lucide/vue'
import { useBuilderFields } from '@/core/composables/useBuilderFields'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

const { builder, dataFields, linkFields } = useBuilderFields()

const hasTree = computed(() => !!builder.doctype?.tree_view)

function toggleTree(enabled: boolean) {
  if (enabled) {
    const firstLink = linkFields.value[0]?.fieldname ?? ''
    builder.updateDocType({ is_tree: true, tree_view: { parent_field: firstLink, title_field: 'name' } })
  } else {
    builder.updateDocType({ is_tree: false, tree_view: null })
  }
}

function updateTree(patch: Record<string, unknown>) {
  if (!builder.doctype?.tree_view) return
  builder.updateDocType({ tree_view: { ...builder.doctype.tree_view, ...patch } })
}

const titleFields = computed(() =>
  dataFields.value.filter((ff) => ['Data', 'Text', 'LongText'].includes(ff.fieldtype)),
)
</script>

<template>
  <div v-if="builder.doctype" class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
      <div class="flex items-center gap-2.5">
        <GitBranch class="size-4 text-muted-foreground" />
        <h3 class="text-sm font-semibold text-foreground">Відображення: Дерево</h3>
        <span
          v-if="hasTree"
          class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-violet-500/15 text-violet-700 dark:text-violet-400"
        >Увімкнено</span>
      </div>
      <Switch :model-value="hasTree" @update:model-value="toggleTree" />
    </div>
    <div v-if="builder.doctype.tree_view" class="p-4 space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Батьківське поле *</label>
          <Select :model-value="builder.doctype.tree_view.parent_field" @update:model-value="updateTree({ parent_field: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue placeholder="Оберіть Link поле" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in linkFields.map((f) => ({ value: f.fieldname, label: f.label }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
          <p class="text-xs text-muted-foreground">Link поле що вказує на цей самий DocType (ієрархія вузлів)</p>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле назви вузла</label>
          <Select :model-value="builder.doctype.tree_view.title_field" @update:model-value="updateTree({ title_field: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [{ value: 'name', label: 'name' }, ...titleFields.map((f) => ({ value: f.fieldname, label: f.label }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  </div>
</template>
