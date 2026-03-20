<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reportsApi } from '@/core/api/reports'
import type { ReportDetail, ReportResult, ReportColumn } from '@/types'
import GButton from '@/components/ui/GButton.vue'
import GSpinner from '@/components/ui/GSpinner.vue'
import GTable from '@/components/ui/GTable.vue'
import type { Column } from '@/components/ui/GTable.vue'

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

const tableColumns = computed((): Column[] =>
  (result.value?.columns ?? []).map((col: ReportColumn) => ({
    key: col.fieldname,
    label: col.label,
    sortable: false,
  }))
)

const tableRows = computed(() =>
  (result.value?.data ?? []) as Record<string, unknown>[]
)

function downloadXlsx() {
  window.open(reportsApi.exportXlsxUrl(reportName), '_blank')
}

onMounted(load)
</script>

<template>
  <div class="p-8 max-w-6xl">
    <!-- Breadcrumb -->
    <div class="flex items-center gap-2 text-sm text-[--grunt-text-secondary] mb-6">
      <button class="hover:text-[--grunt-primary]" @click="router.push('/reports')">Звіти</button>
      <span>/</span>
      <span class="text-[--grunt-text-primary] font-medium">{{ reportName }}</span>
    </div>

    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-semibold text-[--grunt-text-primary]">{{ reportName }}</h1>
        <p v-if="report" class="text-sm text-[--grunt-text-secondary] mt-0.5">
          {{ report.report_type }} звіт
          <span v-if="report.doctype"> · {{ report.doctype }}</span>
        </p>
      </div>
      <div class="flex gap-2">
        <GButton variant="secondary" :loading="isRunning" @click="runReport">Оновити</GButton>
        <GButton variant="secondary" @click="downloadXlsx">Excel ↓</GButton>
      </div>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <GSpinner size="lg" />
    </div>

    <template v-else>
      <!-- Result meta -->
      <div v-if="result" class="text-xs text-[--grunt-text-muted] mb-3">
        Рядків: {{ result.meta.rows }} · {{ result.meta.time_ms }} мс
      </div>

      <!-- Table -->
      <GTable
        v-if="result && result.data.length > 0"
        :columns="tableColumns"
        :rows="tableRows"
        :loading="isRunning"
      />
      <div v-else-if="result" class="text-center py-10 text-[--grunt-text-muted] text-sm">
        Немає даних
      </div>
      <div v-else class="text-center py-10 text-[--grunt-danger] text-sm">
        Помилка виконання звіту
      </div>
    </template>
  </div>
</template>
