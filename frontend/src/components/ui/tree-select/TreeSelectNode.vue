<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, ChevronRight } from '@lucide/vue'
import type { TreeNode } from './types'

const props = defineProps<{
  node: TreeNode
  depth: number
  selectedKey: string | null
  expandedKeys: Record<string, boolean>
  /** Active search text — matching part of the label is emphasised. */
  query?: string
}>()

const emit = defineEmits<{
  select: [key: string]
  toggle: [key: string]
}>()

const { t } = useI18n()

const hasChildren = computed(() => !!props.node.children?.length)
const expanded = computed(() => hasChildren.value && !!props.expandedKeys[props.node.key])
const selected = computed(() => props.node.key === props.selectedKey)

/** Label split around the first case-insensitive match of `query`. */
const parts = computed(() => {
  const label = props.node.label
  const q = props.query?.trim().toLowerCase()
  const i = q ? label.toLowerCase().indexOf(q) : -1
  if (!q || i < 0) return null
  return [label.slice(0, i), label.slice(i, i + q.length), label.slice(i + q.length)]
})
</script>

<template>
  <div role="none">
    <div
      role="treeitem"
      tabindex="-1"
      data-tree-row
      :data-key="node.key"
      :data-selected="selected || undefined"
      :aria-selected="selected"
      :aria-expanded="hasChildren ? expanded : undefined"
      :aria-level="depth + 1"
      class="flex cursor-default items-center gap-1.5 rounded-sm py-1.5 pr-2 text-sm outline-hidden select-none hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground"
      :class="selected && 'font-medium'"
      :style="{ paddingLeft: `${depth * 16 + 4}px` }"
      @click="emit('select', node.key)"
    >
      <button
        v-if="hasChildren"
        type="button"
        tabindex="-1"
        class="shrink-0 rounded-sm p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        :aria-label="expanded ? t('Collapse') : t('Expand')"
        @click.stop="emit('toggle', node.key)"
      >
        <ChevronRight class="size-3.5 transition-transform" :class="expanded && 'rotate-90'" />
      </button>
      <span v-else class="size-4.5 shrink-0" />
      <span class="min-w-0 flex-1 break-words">
        <template v-if="parts">{{ parts[0] }}<mark class="rounded-xs bg-primary/15 text-foreground">{{ parts[1] }}</mark>{{ parts[2] }}</template>
        <template v-else>{{ node.label }}</template>
      </span>
      <span v-if="hasChildren && !expanded" class="shrink-0 text-xs text-muted-foreground tabular-nums">{{ node.children!.length }}</span>
      <Check v-if="selected" class="size-4 shrink-0 text-primary" />
    </div>

    <div v-if="expanded" role="group">
      <TreeSelectNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :depth="depth + 1"
        :selected-key="selectedKey"
        :expanded-keys="expandedKeys"
        :query="query"
        @select="(k) => emit('select', k)"
        @toggle="(k) => emit('toggle', k)"
      />
    </div>
  </div>
</template>
