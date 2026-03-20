<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import client from '@/core/api/client'

interface ActivityEntry {
  id: string
  doctype: string
  doc_id: string
  action: string
  user: string
  created_at: string | null
}

const auth = useAuthStore()
const dtStore = useDocTypeStore()
const router = useRouter()

const docCounts = ref<Record<string, number>>({})
const recentActivity = ref<ActivityEntry[]>([])
const loadingActivity = ref(false)

async function loadCounts() {
  for (const dt of dtStore.doctypes) {
    try {
      const r = await client.get(`/api/v1/docs/${dt.name}`, { params: { per_page: 1 } })
      docCounts.value[dt.name] = r.data?.meta?.total ?? 0
    } catch {
      docCounts.value[dt.name] = 0
    }
  }
}

async function loadActivity() {
  loadingActivity.value = true
  try {
    const r = await client.get('/api/v1/docs/_activity/recent', { params: { limit: 10 } })
    recentActivity.value = (r.data?.data ?? []) as ActivityEntry[]
  } catch {
    // endpoint may not be implemented — ignore
  } finally {
    loadingActivity.value = false
  }
}

onMounted(async () => {
  await dtStore.loadAll()
  await loadCounts()
  await loadActivity()
})

function actionLabel(action: string): string {
  const map: Record<string, string> = { create: 'створив', update: 'оновив', delete: 'видалив' }
  return map[action] ?? action
}
</script>

<template>
  <div class="p-8">
    <h1 class="text-2xl font-semibold text-[--grunt-text-primary] mb-1">
      Вітаємо, {{ auth.user?.full_name ?? 'користувач' }}
    </h1>
    <p class="text-sm text-[--grunt-text-secondary] mb-8">Оберіть розділ нижче або у меню зліва</p>

    <!-- DocType summary cards -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mb-10">
      <div
        v-for="dt in dtStore.doctypes"
        :key="dt.name"
        class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] p-5 cursor-pointer hover:border-[--grunt-primary] hover:shadow-[--grunt-shadow-sm] transition-all"
        @click="router.push(`/${dt.name}`)"
      >
        <h3 class="font-medium text-[--grunt-text-primary]">{{ dt.label }}</h3>
        <p class="text-xs text-[--grunt-text-muted] mt-1">{{ dt.module }}</p>
        <p class="text-2xl font-bold text-[--grunt-primary] mt-3">
          {{ docCounts[dt.name] ?? '—' }}
        </p>
        <p class="text-xs text-[--grunt-text-muted]">записів</p>
      </div>
    </div>

    <!-- Recent activity feed -->
    <div v-if="recentActivity.length > 0">
      <h2 class="text-base font-semibold text-[--grunt-text-primary] mb-3">Остання активність</h2>
      <ul class="space-y-2">
        <li
          v-for="entry in recentActivity"
          :key="entry.id"
          class="flex items-center gap-3 text-sm bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-sm] px-4 py-2"
        >
          <span class="text-[--grunt-text-muted] text-xs whitespace-nowrap">
            {{ entry.created_at ? new Date(entry.created_at).toLocaleString('uk-UA') : '—' }}
          </span>
          <span class="font-medium text-[--grunt-text-primary]">{{ entry.user }}</span>
          <span class="text-[--grunt-text-secondary]">{{ actionLabel(entry.action) }}</span>
          <span class="text-[--grunt-primary]">{{ entry.doctype }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
