<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType } from '@/types'
import GButton from '@/components/ui/GButton.vue'
import GSpinner from '@/components/ui/GSpinner.vue'
import GModal from '@/components/ui/GModal.vue'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import WorkflowBar from '@/components/views/WorkflowBar.vue'

interface ActivityEntry {
  id: string
  action: string
  user: string
  details: Record<string, unknown> | null
  created_at: string | null
}

const props = defineProps<{ doctype: string; id: string | null }>()
const router = useRouter()
const dtStore = useDocTypeStore()
const toast = useToast()
const queryClient = useQueryClient()

const dt = ref<DocType | null>(null)
const { document, form, isLoading, isDirty, isSaving, save, remove } = useDocument(props.doctype, props.id)
const validationErrors = ref<Record<string, string>>({})

// Print menu
const showPrintMenu = ref(false)

// Activity log
const showLog = ref(false)
const activityLog = ref<ActivityEntry[]>([])
const logLoading = ref(false)

async function loadLog() {
  if (!props.id) return
  logLoading.value = true
  try {
    const { default: client } = await import('@/core/api/client')
    const r = await client.get(`/api/v1/docs/${props.doctype}/${props.id}/log`)
    activityLog.value = (r.data?.data ?? []) as ActivityEntry[]
  } catch {
    // ignore
  } finally {
    logLoading.value = false
  }
}

function toggleLog() {
  showLog.value = !showLog.value
  if (showLog.value && activityLog.value.length === 0) loadLog()
}

const showDeleteModal = ref(false)
const showLeaveModal = ref(false)
let pendingNav: (() => void) | null = null
let justSaved = false

onMounted(async () => { dt.value = await dtStore.get(props.doctype) })

// WebSocket real-time
const wsUrl = computed(() => props.id ? `/api/v1/ws/${props.doctype}/${props.id}` : null)
const { lastMessage } = useWebSocket(wsUrl.value)

import { watch } from 'vue'
watch(lastMessage, (msg) => {
  if (!msg || typeof msg !== 'object') return
  const m = msg as Record<string, unknown>
  if (m.event === 'doc_change' && !isDirty.value) {
    toast.info('Документ оновлено іншим користувачем')
    queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
  }
})

const docTitle = computed(() => {
  if (!document.value) return props.id ? '...' : `Новий ${dt.value?.label ?? ''}`
  const tf = dt.value?.title_field
  return (tf && document.value[tf] as string) || document.value.name || `Новий ${dt.value?.label ?? ''}`
})

async function handleSave() {
  validationErrors.value = {}
  try {
    const saved = await save()
    toast.success('Збережено')
    dtStore.invalidate(props.doctype)
    if (!props.id) {
      justSaved = true
      router.replace(`/${props.doctype}/${(saved as { id: string }).id}`)
    }
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { error?: { details?: string[] } } } }
    if (e?.response?.status === 422) {
      const details = e.response.data?.error?.details ?? []
      details.forEach((d: string) => {
        const match = d.match(/^([a-z_]+):\s*(.+)$/)
        if (match) validationErrors.value[match[1]] = match[2]
      })
      toast.error('Перевірте правильність заповнення')
    } else {
      toast.error('Помилка збереження')
    }
  }
}

async function handleDelete() {
  try {
    await remove()
    toast.success('Видалено')
    router.push(`/${props.doctype}`)
  } catch {
    toast.error('Помилка видалення')
  }
  showDeleteModal.value = false
}

onBeforeRouteLeave((_to, _from, next) => {
  if (justSaved) {
    next()
    return
  }
  if (isDirty.value) {
    showLeaveModal.value = true
    pendingNav = () => next()
    next(false)
  } else {
    next()
  }
})

function confirmLeave() {
  showLeaveModal.value = false
  pendingNav?.()
}
</script>

<template>
  <div class="p-8 max-w-3xl">
    <!-- Breadcrumb -->
    <div class="flex items-center gap-2 text-sm text-[--grunt-text-secondary] mb-6">
      <button class="hover:text-[--grunt-primary]" @click="router.push(`/${doctype}`)">
        {{ dt?.label ?? doctype }}
      </button>
      <span>/</span>
      <span class="text-[--grunt-text-primary] font-medium">{{ docTitle }}</span>
    </div>

    <!-- Actions -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-[--grunt-text-primary]">{{ docTitle }}</h1>
      <div class="flex gap-2">
        <!-- Print dropdown (only for saved docs) -->
        <div v-if="id" class="relative">
          <GButton variant="secondary" size="sm" @click="showPrintMenu = !showPrintMenu">↓ Друкувати</GButton>
          <div v-if="showPrintMenu" class="absolute right-0 top-full mt-1 bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] shadow-lg z-50">
            <a :href="`/api/v1/docs/${doctype}/${id}/print?fmt=xlsx`" class="block px-4 py-2 text-sm hover:bg-[--grunt-surface-secondary]" @click="showPrintMenu = false">📊 Excel (.xlsx)</a>
            <a :href="`/api/v1/docs/${doctype}/${id}/print?fmt=pdf`" class="block px-4 py-2 text-sm hover:bg-[--grunt-surface-secondary]" @click="showPrintMenu = false">📄 PDF</a>
            <a :href="`/api/v1/docs/${doctype}/${id}/print?fmt=html`" target="_blank" class="block px-4 py-2 text-sm hover:bg-[--grunt-surface-secondary]" @click="showPrintMenu = false">🌐 HTML</a>
          </div>
        </div>
        <GButton v-if="id && isDirty" variant="secondary" @click="router.go(0)">Скасувати</GButton>
        <GButton v-if="id" variant="danger" @click="showDeleteModal = true">Видалити</GButton>
        <GButton :loading="isSaving" @click="handleSave">Зберегти</GButton>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-16">
      <GSpinner size="lg" />
    </div>

    <template v-else>
      <!-- Workflow bar -->
      <WorkflowBar
        v-if="id && document && dt.workflow"
        :doctype="dt"
        :doc-id="id"
        :doc="document as Record<string, unknown>"
        @transitioned="queryClient.invalidateQueries({ queryKey: ['document', doctype, id] })"
      />

      <!-- Form -->
      <div class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-6">
        <FormRenderer
          :doctype="dt"
          :model-value="form"
          :disabled="isSaving"
          :errors="validationErrors"
          @update:model-value="Object.assign(form, $event)"
        />
      </div>

      <!-- Activity log (only for saved docs) -->
      <div v-if="id" class="mt-4 bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg]">
        <button
          type="button"
          class="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-[--grunt-text-secondary] hover:text-[--grunt-text-primary] transition-colors"
          @click="toggleLog"
        >
          <span>Журнал активності</span>
          <span>{{ showLog ? '▲' : '▼' }}</span>
        </button>
        <div v-if="showLog" class="border-t border-[--grunt-border] px-5 py-3">
          <div v-if="logLoading" class="flex justify-center py-4">
            <GSpinner size="sm" />
          </div>
          <div v-else-if="activityLog.length === 0" class="text-sm text-[--grunt-text-muted] py-2">
            Записів немає
          </div>
          <ul v-else class="space-y-2">
            <li
              v-for="entry in activityLog"
              :key="entry.id"
              class="flex items-start gap-3 text-sm"
            >
              <span class="text-[--grunt-text-muted] text-xs mt-0.5 whitespace-nowrap">
                {{ entry.created_at ? new Date(entry.created_at).toLocaleString('uk-UA') : '—' }}
              </span>
              <span class="font-medium text-[--grunt-text-primary]">{{ entry.user }}</span>
              <span class="text-[--grunt-text-secondary]">{{ entry.action }}</span>
            </li>
          </ul>
        </div>
      </div>
    </template>

    <!-- Delete confirmation -->
    <GModal v-model="showDeleteModal" title="Видалити документ?" size="sm">
      <p class="text-sm text-[--grunt-text-secondary]">Цю дію не можна скасувати.</p>
      <template #footer>
        <GButton variant="secondary" @click="showDeleteModal = false">Скасувати</GButton>
        <GButton variant="danger" @click="handleDelete">Видалити</GButton>
      </template>
    </GModal>

    <!-- Unsaved leave confirmation -->
    <GModal v-model="showLeaveModal" title="Є незбережені зміни" size="sm">
      <p class="text-sm text-[--grunt-text-secondary]">Покинути сторінку без збереження?</p>
      <template #footer>
        <GButton variant="secondary" @click="showLeaveModal = false">Залишитись</GButton>
        <GButton variant="danger" @click="confirmLeave">Покинути</GButton>
      </template>
    </GModal>
  </div>
</template>
