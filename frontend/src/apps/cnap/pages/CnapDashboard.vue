<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import client from '@/core/api/client'
import { Spinner } from '@/components/ui/spinner'

const router = useRouter()
const loading = ref(true)

interface KpiData {
  newToday: number
  inProgress: number
  overdue: number
  completedMonth: number
}

interface AppealRow {
  id: string
  appeal_number: string
  applicant_name: string
  service_name: string
  status: string
  received_date: string
  deadline_date: string
}

interface StatusCount {
  status: string
  count: number
  pct: number
}

const kpi = ref<KpiData>({ newToday: 0, inProgress: 0, overdue: 0, completedMonth: 0 })
const recentAppeals = ref<AppealRow[]>([])
const statusChart = ref<StatusCount[]>([])
const topServices = ref<{ service_name: string; count: number; avg_days: number }[]>([])

const today = new Date().toISOString().split('T')[0]
const monthStart = today.slice(0, 8) + '01'

const statusColors: Record<string, string> = {
  'Нове': '#3b82f6',
  'В роботі': '#eab308',
  'На погодженні': '#a855f7',
  'Виконано': '#22c55e',
  'Відмовлено': '#ef4444',
  'Скасовано': '#6b7280',
}

const maxCount = computed(() => Math.max(...statusChart.value.map(s => s.count), 1))

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    'Нове': 'bg-blue-100 text-blue-700',
    'В роботі': 'bg-yellow-100 text-yellow-700',
    'На погодженні': 'bg-purple-100 text-purple-700',
    'Виконано': 'bg-green-100 text-green-700',
    'Відмовлено': 'bg-red-100 text-red-700',
    'Скасовано': 'bg-gray-100 text-gray-600',
  }
  return map[status] || 'bg-gray-100 text-gray-600'
}

function isOverdue(row: AppealRow): boolean {
  if (!row.deadline_date) return false
  if (['Виконано', 'Відмовлено', 'Скасовано'].includes(row.status)) return false
  return row.deadline_date < today
}

async function fetchKpi() {
  try {
    const [newRes, inProgressRes, overdueRes, completedRes] = await Promise.all([
      client.get('/api/v1/docs/Appeal', {
        params: { 'filter[status]': 'Нове', 'filter[received_date__gte]': today, per_page: 1 },
      }),
      client.get('/api/v1/docs/Appeal', {
        params: { 'filter[status]': 'В роботі', per_page: 1 },
      }),
      client.get('/api/v1/docs/Appeal', {
        params: {
          'filter[deadline_date__lt]': today,
          'filter[status__in]': 'Нове,В роботі,На погодженні',
          per_page: 1,
        },
      }),
      client.get('/api/v1/docs/Appeal', {
        params: {
          'filter[status]': 'Виконано',
          'filter[modified_at__gte]': monthStart,
          per_page: 1,
        },
      }),
    ])
    kpi.value = {
      newToday: newRes.data?.meta?.total ?? 0,
      inProgress: inProgressRes.data?.meta?.total ?? 0,
      overdue: overdueRes.data?.meta?.total ?? 0,
      completedMonth: completedRes.data?.meta?.total ?? 0,
    }
  } catch {
    // ignore
  }
}

async function fetchRecent() {
  try {
    const r = await client.get('/api/v1/docs/Appeal', {
      params: {
        per_page: 10,
        sort: 'received_date',
        order: 'desc',
        fields: 'appeal_number,applicant_name,service_name,status,received_date,deadline_date',
      },
    })
    recentAppeals.value = r.data?.data ?? []
  } catch {
    // ignore
  }
}

async function fetchStatusChart() {
  try {
    await client.get('/api/v1/docs/Appeal', {
      params: { per_page: 1 },
    })
    // Build status counts from all appeals
    const allR = await client.get('/api/v1/docs/Appeal', {
      params: { per_page: 10000, fields: 'status' },
    })
    const rows: { status: string }[] = allR.data?.data ?? []
    const counts: Record<string, number> = {}
    for (const row of rows) {
      counts[row.status] = (counts[row.status] || 0) + 1
    }
    const total = rows.length || 1
    statusChart.value = Object.entries(counts)
      .map(([status, count]) => ({
        status,
        count,
        pct: Math.round((count * 100) / total),
      }))
      .sort((a, b) => b.count - a.count)
  } catch {
    // ignore
  }
}

async function fetchTopServices() {
  try {
    const r = await client.get('/api/v1/docs/Appeal', {
      params: { per_page: 10000, fields: 'service_name' },
    })
    const rows: { service_name: string }[] = r.data?.data ?? []
    const counts: Record<string, number> = {}
    for (const row of rows) {
      if (row.service_name) {
        counts[row.service_name] = (counts[row.service_name] || 0) + 1
      }
    }
    topServices.value = Object.entries(counts)
      .map(([service_name, count]) => ({ service_name, count, avg_days: 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10)
  } catch {
    // ignore
  }
}

onMounted(async () => {
  await Promise.all([fetchKpi(), fetchRecent(), fetchStatusChart(), fetchTopServices()])
  loading.value = false
})
</script>

<template>
  <div class="p-8 max-w-6xl">
    <h1 class="text-2xl font-bold text-[--grunt-text-primary] mb-6">ЦНАП — Дашборд</h1>

    <div v-if="loading" class="flex justify-center py-16">
      <Spinner size="lg" />
    </div>

    <template v-else>
      <!-- KPI Cards -->
      <div class="grid grid-cols-4 gap-4 mb-8">
        <button
          class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 text-left hover:border-blue-400 transition-colors"
          @click="router.push('/Appeal?filter[status]=Нове&filter[received_date__gte]=' + today)"
        >
          <div class="text-sm text-[--grunt-text-secondary] mb-1">Нових сьогодні</div>
          <div class="text-3xl font-bold text-blue-600">{{ kpi.newToday }}</div>
        </button>

        <button
          class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 text-left hover:border-yellow-400 transition-colors"
          @click="router.push('/Appeal?filter[status]=В роботі')"
        >
          <div class="text-sm text-[--grunt-text-secondary] mb-1">В роботі</div>
          <div class="text-3xl font-bold text-yellow-600">{{ kpi.inProgress }}</div>
        </button>

        <button
          class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 text-left hover:border-red-400 transition-colors"
          @click="router.push('/Appeal?filter[deadline_date__lt]=' + today + '&filter[status__in]=Нове,В роботі,На погодженні')"
        >
          <div class="text-sm text-[--grunt-text-secondary] mb-1">Прострочено</div>
          <div class="text-3xl font-bold text-red-600">{{ kpi.overdue }}</div>
        </button>

        <button
          class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 text-left hover:border-green-400 transition-colors"
          @click="router.push('/Appeal?filter[status]=Виконано')"
        >
          <div class="text-sm text-[--grunt-text-secondary] mb-1">Виконано цього місяця</div>
          <div class="text-3xl font-bold text-green-600">{{ kpi.completedMonth }}</div>
        </button>
      </div>

      <div class="grid grid-cols-3 gap-6">
        <!-- Recent Appeals (2/3 width) -->
        <div class="col-span-2">
          <div class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5">
            <h2 class="text-lg font-semibold text-[--grunt-text-primary] mb-4">Останні звернення</h2>
            <table class="w-full text-sm">
              <thead>
                <tr class="text-[--grunt-text-secondary] border-b border-[--grunt-border]">
                  <th class="text-left py-2 px-2">Номер</th>
                  <th class="text-left py-2 px-2">Заявник</th>
                  <th class="text-left py-2 px-2">Послуга</th>
                  <th class="text-left py-2 px-2">Статус</th>
                  <th class="text-left py-2 px-2">Дата</th>
                  <th class="text-left py-2 px-2">Дедлайн</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in recentAppeals"
                  :key="row.id"
                  class="border-b border-[--grunt-border] hover:bg-[--grunt-surface-secondary] cursor-pointer transition-colors"
                  :class="{ 'bg-red-50': isOverdue(row) }"
                  @click="router.push(`/Appeal/${row.id}`)"
                >
                  <td class="py-2 px-2 font-medium">{{ row.appeal_number || row.id?.slice(0, 8) }}</td>
                  <td class="py-2 px-2 truncate max-w-[150px]">{{ row.applicant_name }}</td>
                  <td class="py-2 px-2 truncate max-w-[150px]">{{ row.service_name }}</td>
                  <td class="py-2 px-2">
                    <span
                      class="inline-block px-2 py-0.5 rounded text-xs font-medium"
                      :class="statusBadgeClass(row.status)"
                    >{{ row.status }}</span>
                  </td>
                  <td class="py-2 px-2 whitespace-nowrap">{{ row.received_date }}</td>
                  <td class="py-2 px-2 whitespace-nowrap" :class="{ 'text-red-600 font-medium': isOverdue(row) }">
                    {{ row.deadline_date }}
                  </td>
                </tr>
                <tr v-if="recentAppeals.length === 0">
                  <td colspan="6" class="py-8 text-center text-[--grunt-text-muted]">
                    Звернень поки немає
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Status Chart (1/3 width) -->
        <div class="col-span-1">
          <div class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5">
            <h2 class="text-lg font-semibold text-[--grunt-text-primary] mb-4">По статусах</h2>
            <div class="space-y-3">
              <div v-for="item in statusChart" :key="item.status" class="flex items-center gap-2">
                <span class="text-xs text-[--grunt-text-secondary] w-28 truncate">{{ item.status }}</span>
                <div class="flex-1 h-5 bg-[--grunt-surface-secondary] rounded overflow-hidden">
                  <div
                    class="h-full rounded"
                    :style="{
                      width: (item.count / maxCount * 100) + '%',
                      backgroundColor: statusColors[item.status] || '#6b7280',
                    }"
                  ></div>
                </div>
                <span class="text-xs font-medium text-[--grunt-text-primary] w-8 text-right">{{ item.count }}</span>
              </div>
              <p v-if="statusChart.length === 0" class="text-sm text-[--grunt-text-muted]">Немає даних</p>
            </div>
          </div>

          <!-- Top Services -->
          <div class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 mt-6">
            <h2 class="text-lg font-semibold text-[--grunt-text-primary] mb-4">Топ послуги</h2>
            <div class="space-y-2">
              <div
                v-for="(svc, idx) in topServices"
                :key="svc.service_name"
                class="flex items-center justify-between text-sm"
              >
                <span class="text-[--grunt-text-secondary] truncate mr-2">
                  {{ idx + 1 }}. {{ svc.service_name }}
                </span>
                <span class="font-medium text-[--grunt-text-primary] flex-shrink-0">{{ svc.count }}</span>
              </div>
              <p v-if="topServices.length === 0" class="text-sm text-[--grunt-text-muted]">Немає даних</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
