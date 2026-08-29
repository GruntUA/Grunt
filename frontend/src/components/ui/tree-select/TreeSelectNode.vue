<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import type { TreeNode } from './types'

const props = defineProps<{
  node: TreeNode
  depth: number
  selectedKey: string | null
  expandedKeys: Record<string, boolean>
}>()

const emit = defineEmits<{
  select: [key: string]
  toggle: [key: string]
}>()
</script>

<template>
  <div>
    <div
      class="flex items-center gap-1 rounded-sm py-1.5 pr-2 hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
      :class="node.key === selectedKey ? 'bg-accent/60 font-medium' : ''"
      :style="{ paddingLeft: `${depth * 16 + 8}px` }"
      @click="emit('select', node.key)"
    >
      <button
        v-if="node.children?.length"
        type="button"
        class="shrink-0 p-0.5 rounded hover:bg-muted"
        @click.stop="emit('toggle', node.key)"
      >
        <ChevronRight class="size-3.5 transition-transform" :class="expandedKeys[node.key] ? 'rotate-90' : ''" />
      </button>
      <span v-else class="inline-block size-4 shrink-0" />
      <span class="truncate">{{ node.label }}</span>
    </div>

    <template v-if="node.children?.length && expandedKeys[node.key]">
      <TreeSelectNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :depth="depth + 1"
        :selected-key="selectedKey"
        :expanded-keys="expandedKeys"
        @select="(k) => emit('select', k)"
        @toggle="(k) => emit('toggle', k)"
      />
    </template>
  </div>
</template>
