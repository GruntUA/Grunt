<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { FileItem } from '@/core/api/files'
import { docUrl } from '@/core/workspaceUrl'
import FileExplorer from '@/components/files/FileExplorer.vue'

const props = defineProps<{
  doctype: string
  workspace?: string
  refreshKey?: number
}>()

const router = useRouter()
const explorer = ref<InstanceType<typeof FileExplorer> | null>(null)

// The header's Refresh button
watch(() => props.refreshKey, () => explorer.value?.reload())

// Double-click / Enter on a file opens its document.
function openFile(file: FileItem) {
  router.push(docUrl(props.doctype, file.id, props.workspace))
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden rounded-md border bg-card shadow-sm [&>*>:first-child]:border-t-0">
    <FileExplorer ref="explorer" mode="file" multiple view="tiles" @activate="openFile" />
  </div>
</template>
