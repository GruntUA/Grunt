<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reportsApi } from '@/core/api/reports'
import type { ReportDetail, ReportResult, ReportColumn } from '@/types'
import { Loader2 } from '@lucide/vue'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const reportName = route.params.name as string

const report = ref<ReportDetail | null>(null)
const result = ref<ReportResult | null>(null)
const isLoading = ref(true)
const isRunning = ref(false)
const filters = ref<Record<string, string>>({})

async function load() {
  isLoading.value = true
  try {
    const r = await reportsApi.get(reportName)
    report.value = r.data
    // Auto-run on load
    await runReport()
  } finally {
    isLoading.value = false
  }
}

async function runReport() {
  isRunning.value = true
  try {
    const r = await reportsApi.run(reportName, filters.value)
    result.value = {
      columns: r.columns,
      data: r.data,
      meta: r.meta,
    }
  } catch (e) {
    result.value = null
  } finally {
    isRunning.value = false
  }
}

const tableColumns = computed(() =>
  (result.value?.columns ?? []).map((col: ReportColumn) => ({
    key: col.fieldname,
    label: col.label,
  }))
)

const tableRows = computed(() =>
  (result.value?.data ?? []) as Record<string, unknown>[]
)

function downloadXlsx() {
  const url = reportsApi.exportXlsxUrl(reportName)
  window.open(`${url}?token=${auth.token}`, '_blank')
}

onMounted(load)
</script>

<template>
  <div class="p-8 max-w-6xl">
    <!-- Breadcrumb -->
    <div class="flex items-center gap-2 text-sm text-muted-foreground mb-6">
      <button class="hover:text-primary" @click="router.push('/reports')">Звіти</button>
      <span>/</span>
      <span class="text-foreground font-medium">{{ reportName }}</span>
    </div>

    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-semibold text-foreground">{{ reportName }}</h1>
        <p v-if="report" class="text-sm text-muted-foreground mt-0.5">
          {{ report.report_type }} звіт
          <span v-if="report.doctype"> · {{ report.doctype }}</span>
        </p>
      </div>
      <div class="flex gap-2">
        <Button severity="secondary" :disabled="isRunning" @click="runReport"><Loader2 v-if="isRunning" class="size-4 animate-spin" />Оновити</Button>
        <Button severity="secondary" @click="downloadXlsx">Excel ↓</Button>
      </div>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <ProgressSpinner class="size-10!" />
    </div>

    <template v-else>
      <!-- Result meta -->
      <div v-if="result" class="text-xs text-muted-foreground mb-3">
        Рядків: {{ result.meta.rows }} · {{ result.meta.time_ms }} мс
      </div>

      <!-- Table -->
      <DataTable v-if="result && result.data.length > 0" :value="tableRows" size="small" stripedRows class="border border-border/50 rounded-lg overflow-hidden">
        <Column v-for="col in tableColumns" :key="col.key" :field="col.key" :header="col.label" />
      </DataTable>
      <div v-else-if="result" class="text-center py-10 text-muted-foreground text-sm">
        Немає даних
      </div>
      <div v-else class="text-center py-10 text-destructive text-sm">
        Помилка виконання звіту
      </div>
    </template>
  </div>
</template>
