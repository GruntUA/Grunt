<script setup lang="ts">
import DocTypeList from '@/pages/desk/DocTypeList.vue'

defineProps<{
  workspaceName: string
  doctype: string
}>()
</script>

<template>
  <DocTypeList :doctype="doctype" :workspace="workspaceName" />
</template>
