<script setup lang="ts">
import { onMounted } from 'vue'
import WorkspaceBreadcrumb from '@/components/workspace/WorkspaceBreadcrumb.vue'
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
  } catch {
    // ignore
  }
})
</script>

<template>
  <div class="p-8">
    <WorkspaceBreadcrumb
      :workspace-name="workspaceName"
      :doctype="doctype"
      :doc-id="id"
    />
    <DocTypeForm :doctype="doctype" :id="id" :workspace="workspaceName" />
  </div>
</template>
