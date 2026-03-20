<script setup lang="ts">
import WorkspaceBreadcrumb from '@/components/workspace/WorkspaceBreadcrumb.vue'
import DocTypeList from '@/pages/desk/DocTypeList.vue'

defineProps<{
  workspaceName: string
  doctype: string
}>()
</script>

<template>
  <div class="p-8">
    <WorkspaceBreadcrumb :workspace-name="workspaceName" :doctype="doctype" />
    <DocTypeList :doctype="doctype" :workspace="workspaceName" />
  </div>
</template>
