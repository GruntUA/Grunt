<script setup lang="ts">
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
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
  <div class="px-4 py-3 sm:px-6 sm:py-4 lg:px-8 lg:py-4">
    <AppBreadcrumb
      :workspace-name="workspaceName"
      :doctype="doctype"
      :doc-id="id"
    />
    <DocTypeForm
      :doctype="doctype"
      :id="id"
      :workspace="workspaceName"
      class="p-0! mt-2!"
      @loaded="onLoaded"
      @notfound="onNotFound"
    />
  </div>
</template>
