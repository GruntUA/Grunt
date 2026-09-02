<script setup lang="ts">
import DocTypeForm from '@/pages/desk/DocTypeForm.vue'
import { pushRecent, removeRecent } from '@/core/recentDocs'

const props = defineProps<{
  workspaceName: string
  doctype: string
  id: string | null
}>()

// Record the recent-docs entry only once the document is loaded, so we store
// its real title (title_field) instead of the opaque id.
function onLoaded(payload: { doctype: string; id: string; title: string }) {
  pushRecent({
    workspace: props.workspaceName,
    doctype: payload.doctype,
    id: payload.id,
    title: payload.title,
  })
}

// A document that fails to load (e.g. deleted) is pruned from history so the
// recent list never links to a 404.
function onNotFound(payload: { id: string }) {
  removeRecent(payload.id)
}
</script>

<template>
  <DocTypeForm
    :doctype="doctype"
    :id="id"
    :workspace="workspaceName"
    @loaded="onLoaded"
    @notfound="onNotFound"
  />
</template>
