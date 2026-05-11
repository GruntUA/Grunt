<script setup lang="ts">
import { onMounted } from 'vue'
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
import DocTypeForm from '@/pages/desk/DocTypeForm.vue'

const props = defineProps<{
  workspaceName: string
  doctype: string
  id: string | null
}>()

// Track recent docs in localStorage
onMounted(() => {
  if (!props.id) return

  try {
    const key = 'grunt_recent_docs'
    const saved = localStorage.getItem(key)
    const recent: Array<{ workspace: string; doctype: string; id: string; title: string; ts: number }> = saved ? JSON.parse(saved) : []

    // Remove existing entry for this doc
    const filtered = recent.filter(d => d.id !== props.id)

    // Add to front
    filtered.unshift({
      workspace: props.workspaceName,
      doctype: props.doctype,
      id: props.id,
      title: props.id,
      ts: Date.now(),
    })

    // Keep only last 20
    localStorage.setItem(key, JSON.stringify(filtered.slice(0, 20)))
    window.dispatchEvent(new Event('grunt_recent_docs_changed'))
  } catch {
    // ignore
  }
})
</script>

<template>
  <div class="px-4 py-3 sm:px-6 sm:py-4 lg:px-8 lg:py-4">
    <AppBreadcrumb
      :workspace-name="workspaceName"
      :doctype="doctype"
      :doc-id="id"
    />
    <DocTypeForm :doctype="doctype" :id="id" :workspace="workspaceName" class="p-0! mt-2!" />
  </div>
</template>
