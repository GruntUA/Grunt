<script setup lang="ts">
import WorkspaceBreadcrumb from '@/components/workspace/WorkspaceBreadcrumb.vue'

defineProps<{
  workspaceName: string
  reportName: string
}>()
</script>

<template>
  <div class="p-8">
    <WorkspaceBreadcrumb :workspace-name="workspaceName" :doctype="reportName" />
    <!-- Reuse existing ReportView if available -->
    <div class="text-sm text-muted-foreground/70">
      Звіт: {{ reportName }}
    </div>
  </div>
</template>
