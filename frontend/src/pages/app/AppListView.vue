<script setup lang="ts">
import { ref, watch } from 'vue'
import AppFormView from '@/pages/app/AppFormView.vue'
import DocTypeList from '@/pages/desk/DocTypeList.vue'
import { useDocTypeStore } from '@/stores/doctype'

const props = defineProps<{
  workspaceName: string
  doctype: string
}>()

const dtStore = useDocTypeStore()

// A singleton has no list: its only document is shown right at /app/<ws>/<DocType>.
const isSingleton = ref<boolean | null>(null)

watch(() => props.doctype, async (doctype) => {
  isSingleton.value = null
  try {
    isSingleton.value = !!(await dtStore.get(doctype)).is_singleton
  } catch {
    isSingleton.value = false
  }
}, { immediate: true })
</script>

<template>
  <AppFormView v-if="isSingleton" :key="doctype" :workspace-name="workspaceName" :doctype="doctype" :id="doctype" />
  <DocTypeList v-else-if="isSingleton === false" :doctype="doctype" :workspace="workspaceName" />
</template>
