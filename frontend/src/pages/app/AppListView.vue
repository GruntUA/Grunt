<script setup lang="ts">
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
import DocTypeList from '@/pages/desk/DocTypeList.vue'

defineProps<{
  workspaceName: string
  doctype: string
}>()
</script>

<template>
  <div class="px-4 py-3 sm:px-6 sm:py-4 lg:px-8 lg:py-4">
    <AppBreadcrumb :workspace-name="workspaceName" :doctype="doctype" />
    <DocTypeList :doctype="doctype" :workspace="workspaceName" class="p-0! mt-2!" />
  </div>
</template>
