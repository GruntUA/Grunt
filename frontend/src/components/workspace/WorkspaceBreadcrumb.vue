<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import Breadcrumb from 'primevue/breadcrumb'

const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
}>()

const wsStore = useWorkspaceStore()

const workspaceLabel = computed(() => wsStore.active?.label ?? props.workspaceName)
const workspaceIcon = computed(() => wsStore.active?.icon ?? '')

const doctypeLabel = computed(() => {
  if (!props.doctype || !wsStore.active) return props.doctype
  const item = wsStore.active.items.find(i => i.link_to === props.doctype)
  return item?.label ?? props.doctype
})

const items = computed(() => {
  const result: Array<{ label?: string; icon?: string; route?: string }> = [
    {
      label: workspaceLabel.value,
      icon: workspaceIcon.value || undefined,
      route: `/${props.workspaceName}`,
    },
  ]
  if (props.doctype) {
    result.push({
      label: doctypeLabel.value,
      route: props.docId ? `/${props.workspaceName}/list/${props.doctype}` : undefined,
    })
  }
  if (props.docId) {
    result.push({ label: String(props.docId) })
  }
  return result
})
</script>

<template>
  <Breadcrumb :model="items" class="mb-2 !bg-transparent !border-none !p-0">
    <template #item="{ item, props: ip }">
      <router-link
        v-if="item.route"
        v-slot="rp"
        :to="item.route"
        custom
      >
        <a v-bind="ip.action" :href="rp.href" class="flex items-center gap-1.5 font-medium capitalize" @click="rp.navigate">
          <span v-if="item.icon" class="text-sm">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </a>
      </router-link>
      <span v-else class="font-semibold text-foreground/90 truncate max-w-[300px]">{{ item.label }}</span>
    </template>
  </Breadcrumb>
</template>
