<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { reportsApi } from '@/core/api/reports'
import type { ReportSummary } from '@/types'
import GSpinner from '@/components/ui/GSpinner.vue'

const router = useRouter()
const reports = ref<ReportSummary[]>([])
const isLoading = ref(true)

const typeIcon: Record<string, string> = {
  Query: '🔍',
  Script: '📜',
  List: '📋',
}

async function load() {
  isLoading.value = true
  try {
    const r = await reportsApi.list()
    reports.value = r.data ?? []
  } finally {
    isLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="p-8 max-w-5xl">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-[--grunt-text-primary]">Звіти</h1>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <GSpinner size="lg" />
    </div>

    <div v-else-if="reports.length === 0" class="text-center py-16 text-[--grunt-text-muted]">
      <p class="text-lg mb-2">Звітів немає</p>
      <p class="text-sm">Додайте звіти через API або через Studio.</p>
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
      <div
        v-for="report in reports"
        :key="report.id"
        class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 cursor-pointer hover:border-[--grunt-primary] hover:shadow-sm transition-all"
        @click="router.push(`/reports/${encodeURIComponent(report.report_name)}`)"
      >
        <div class="flex items-center gap-2 mb-2">
          <span class="text-2xl">{{ typeIcon[report.report_type] ?? '📊' }}</span>
          <span class="text-xs font-medium text-[--grunt-text-muted] uppercase">{{ report.report_type }}</span>
        </div>
        <h3 class="font-medium text-[--grunt-text-primary] mb-1">{{ report.report_name }}</h3>
        <p v-if="report.doctype" class="text-xs text-[--grunt-text-secondary]">{{ report.doctype }}</p>
      </div>
    </div>
  </div>
</template>
