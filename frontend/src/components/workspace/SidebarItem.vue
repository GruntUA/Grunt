<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'

const props = defineProps<{
  item: WorkspaceLink
  workspaceName: string
  count?: number
  collapsed?: boolean
  color?: string
}>()

const router = useRouter()
const route = useRoute()

const isActive = computed(() => {
  if (props.item.type === 'DocType') {
    return route.params.doctype === props.item.link_to
  }
  if (props.item.type === 'Report') {
    return route.params.reportName === props.item.link_to
  }
  return false
})

function navigate() {
  switch (props.item.type) {
    case 'DocType':
      router.push(`/${props.workspaceName}/list/${props.item.link_to}`)
      break
    case 'Report':
      router.push(`/${props.workspaceName}/report/${props.item.link_to}`)
      break
    case 'URL':
      window.open(props.item.link_to, '_blank')
      break
    case 'Dashboard':
      router.push(`/${props.workspaceName}/dashboard/${props.item.link_to}`)
      break
  }
}

function createNew(e: Event) {
  e.stopPropagation()
  router.push(`/${props.workspaceName}/list/${props.item.link_to}/new`)
}

const displayCount = computed(() => {
  if (!props.count || props.count <= 0) return ''
  return props.count > 99 ? '99+' : String(props.count)
})
</script>

<template>
  <button
    class="sidebar-item group w-full flex items-center gap-2 text-left transition-colors"
    :class="[
      isActive
        ? 'sidebar-item--active'
        : 'hover:bg-[--grunt-surface-secondary] text-[--grunt-text-secondary]',
      collapsed ? 'justify-center px-0 h-10' : 'px-3'
    ]"
    :style="{ height: collapsed ? '40px' : 'var(--grunt-sidebar-item-h)' }"
    :title="collapsed ? item.label : undefined"
    @click="navigate"
  >
    <span class="text-sm shrink-0" :class="{ 'text-base': collapsed }">{{ item.icon }}</span>

    <template v-if="!collapsed">
      <span class="text-sm truncate flex-1">{{ item.label }}</span>

      <!-- Count badge -->
      <span
        v-if="displayCount"
        class="text-xs font-medium px-1.5 py-0.5 rounded-full shrink-0"
        :style="{
          backgroundColor: (color ?? 'var(--grunt-primary)') + '18',
          color: color ?? 'var(--grunt-primary)'
        }"
      >{{ displayCount }}</span>

      <!-- New button -->
      <button
        v-if="item.show_new_btn"
        class="opacity-0 group-hover:opacity-100 text-xs text-[--grunt-text-muted] hover:text-[--grunt-primary] transition-opacity shrink-0 px-1"
        title="Створити новий"
        @click="createNew"
      >+</button>
    </template>
  </button>
</template>

<style scoped>
.sidebar-item--active {
  background: var(--grunt-primary-light);
  border-left: 2px solid var(--grunt-primary);
  border-radius: 0;
  color: var(--grunt-primary);
  font-weight: 500;
}
</style>
