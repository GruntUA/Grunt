<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{ workspaceName: string }>()
const router = useRouter()
const wsStore = useWorkspaceStore()

function navigateItem(item: { type: string; link_to: string }) {
  if (item.type === 'DocType') router.push(`/${props.workspaceName}/list/${item.link_to}`)
  else if (item.type === 'Report') router.push(`/${props.workspaceName}/report/${item.link_to}`)
  else if (item.type === 'URL') window.open(item.link_to, '_blank')
}

onMounted(async () => {
  // Wait for workspace to be loaded
  if (!wsStore.active) {
    await wsStore.setActive(props.workspaceName)
  }

  // Redirect to first DocType item
  if (wsStore.active) {
    const firstDocType = wsStore.active.items
      .sort((a, b) => a.sequence - b.sequence)
      .find(item => item.type === 'DocType' && item.link_to)

    if (firstDocType) {
      router.replace(`/${props.workspaceName}/list/${firstDocType.link_to}`)
      return
    }
  }
})
</script>

<template>
  <div class="p-8">
    <div v-if="wsStore.active" class="max-w-lg">
      <div class="flex items-center gap-3 mb-4">
        <span class="text-4xl">{{ wsStore.active.icon }}</span>
        <div>
          <h1 class="text-xl font-semibold text-foreground">{{ wsStore.active.label }}</h1>
          <p class="text-sm text-muted-foreground">{{ wsStore.active.description }}</p>
        </div>
      </div>

      <div class="space-y-1 mt-6">
        <button
          v-for="item in wsStore.active.items.filter(i => i.type !== 'Divider')"
          :key="item.link_to"
          class="w-full flex items-center gap-3 px-4 py-3 text-sm bg-card border border-border rounded-md hover:border-primary transition-colors text-left"
          @click="navigateItem(item)"
        >
          <span>{{ item.icon }}</span>
          <span class="text-foreground">{{ item.label }}</span>
          <span class="text-xs text-muted-foreground/70 ml-auto">{{ item.type }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
