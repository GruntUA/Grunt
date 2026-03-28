<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useClientScripts } from '@/core/composables/useClientScripts'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Loader2,
  ChevronRight,
  Printer,
  FileSpreadsheet,
  FileText,
  Globe,
  Trash2,
  ChevronDown,
  History,
} from 'lucide-vue-next'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import WorkflowBar from '@/components/views/WorkflowBar.vue'

interface ActivityEntry {
  id: string
  action: string
  user: string
  details: Record<string, unknown> | null
  created_at: string | null
}

const props = defineProps<{ doctype: string; id: string | null; workspace?: string }>()
const router = useRouter()
const dtStore = useDocTypeStore()
const toast = useToast()
const queryClient = useQueryClient()

const dt = ref<DocType | null>(null)
const { document, form, isLoading, isDirty, isSaving, save, remove } = useDocument(props.doctype, props.id)
const validationErrors = ref<Record<string, string>>({})

// Client scripts
const {
  buttons: scriptButtons,
  displayOverrides,
  reqdOverrides,
  runEvent: runScriptEvent,
} = useClientScripts(props.doctype, {
  getDoc: () => form.value,
  getFields: () => (dt.value?.fields ?? []) as Record<string, unknown>[],
  isNew: () => !props.id,
  setValue: (field, value) => { form.value[field] = value },
  save: () => handleSave(),
})

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
let pendingRoute: string | null = null
let allowLeave = false

onMounted(async () => {
  dt.value = await dtStore.get(props.doctype)
  // Run client scripts on_load after DocType metadata is available
  await runScriptEvent('on_load')
})

// WebSocket real-time
const wsUrl = computed(() => props.id ? `/api/v1/ws/${props.doctype}/${props.id}` : null)
const { lastMessage } = useWebSocket(wsUrl.value)

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

function focusFirstError() {
  nextTick(() => {
    const firstKey = Object.keys(validationErrors.value)[0]
    if (!firstKey) return
    const el = window.document.querySelector(`[data-fieldname="${firstKey}"]`) as HTMLElement | null
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // Shake animation for attention
    el.classList.add('field-shake')
    el.addEventListener('animationend', () => el.classList.remove('field-shake'), { once: true })
    const input = el.querySelector('input, textarea, select, [contenteditable]') as HTMLElement | null
    input?.focus()
  })
}

async function handleSave() {
  validationErrors.value = {}

  // Run client script validation
  const valid = await runScriptEvent('validate')
  if (!valid) return

  await runScriptEvent('before_save')

  try {
    const saved = await save()
    toast.success('Збережено')
    runScriptEvent('after_save')
    dtStore.invalidate(props.doctype)
    if (!props.id) {
      allowLeave = true
      const newId = (saved as { id: string }).id
      const path = props.workspace
        ? `/${props.workspace}/list/${props.doctype}/${newId}`
        : `/${props.doctype}/${newId}`
      router.replace(path)
    }
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { detail?: string | string[] } } }
    if (e?.response?.status === 422) {
      const detail = e.response.data?.detail
      const details: string[] = Array.isArray(detail) ? detail : (typeof detail === 'string' ? [detail] : [])
      let hasFieldErrors = false
      details.forEach((d: string) => {
        const match = d.match(/^([a-z_]+):\s*(.+)$/)
        if (match) {
          validationErrors.value[match[1]] = match[2]
          hasFieldErrors = true
        }
      })
      if (hasFieldErrors) {
        toast.error('Перевірте правильність заповнення')
        focusFirstError()
      } else if (details.length > 0) {
        toast.error(details.join('; '))
      } else {
        toast.error('Помилка валідації')
      }
    } else {
      toast.error('Помилка збереження')
    }
  }
}

async function handleDelete() {
  try {
    await remove()
    toast.success('Видалено')
    router.push(props.workspace ? `/${props.workspace}/list/${props.doctype}` : `/${props.doctype}`)
  } catch {
    toast.error('Помилка видалення')
  }
  showDeleteModal.value = false
}

onBeforeRouteLeave((to, _from, next) => {
  if (allowLeave) {
    next()
    return
  }
  if (isDirty.value) {
    showLeaveModal.value = true
    pendingRoute = to.fullPath
    next(false)
  } else {
    next()
  }
})

function confirmLeave() {
  showLeaveModal.value = false
  allowLeave = true
  if (pendingRoute) {
    router.push(pendingRoute)
    pendingRoute = null
  }
}

function onFormUpdate(updated: Record<string, unknown>) {
  // Detect which field changed
  const changedFields: string[] = []
  for (const key of Object.keys(updated)) {
    if (updated[key] !== form.value[key]) {
      changedFields.push(key)
    }
  }
  Object.assign(form.value, updated)
  // Fire on_change for each changed field
  for (const field of changedFields) {
    runScriptEvent('on_change', field)
  }
}
</script>

<template>
  <div class="p-4 sm:p-6 lg:p-8 max-w-full lg:max-w-4xl xl:max-w-5xl">
    <!-- Breadcrumb -->
    <nav class="flex items-center gap-1.5 text-sm mb-6">
      <button
        class="text-muted-foreground hover:text-primary transition-colors"
        @click="router.push(workspace ? `/${workspace}/list/${doctype}` : `/${doctype}`)"
      >
        {{ dt?.label ?? doctype }}
      </button>
      <ChevronRight class="size-3.5 text-muted-foreground/60" />
      <span class="text-foreground font-medium truncate">{{ docTitle }}</span>
      <Badge v-if="isDirty" variant="outline" class="ml-2 text-xs border-amber-400 text-amber-600">Не збережено</Badge>
    </nav>

    <!-- Header + Actions -->
    <div class="flex items-center justify-between mb-6 gap-4">
      <h1 class="text-xl font-semibold text-foreground truncate">{{ docTitle }}</h1>
      <div class="flex items-center gap-2 shrink-0">
        <!-- Client script buttons -->
        <Button
          v-for="btn in scriptButtons"
          :key="btn.label"
          :variant="(btn.variant as any) ?? 'outline'"
          size="sm"
          @click="btn.action"
        >
          {{ btn.label }}
        </Button>

        <!-- Print dropdown -->
        <DropdownMenu v-if="id">
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm">
              <Printer class="size-4 mr-1.5" />
              Друкувати
              <ChevronDown class="size-3.5 ml-1" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=xlsx`">
              <FileSpreadsheet class="size-4 mr-2" />
              Excel (.xlsx)
            </DropdownMenuItem>
            <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=pdf`">
              <FileText class="size-4 mr-2" />
              PDF
            </DropdownMenuItem>
            <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=html`" target="_blank">
              <Globe class="size-4 mr-2" />
              HTML
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button v-if="id && isDirty" variant="ghost" size="sm" @click="router.go(0)">Скасувати</Button>
        <Button v-if="id" variant="outline" size="sm" class="text-destructive hover:text-destructive" @click="showDeleteModal = true">
          <Trash2 class="size-4 mr-1.5" />
          Видалити
        </Button>
        <Button :disabled="isSaving" size="sm" @click="handleSave">
          <Loader2 v-if="isSaving" class="size-4 animate-spin mr-1.5" />
          Зберегти
        </Button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-16">
      <Spinner size="lg" />
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
      <div class="bg-card border border-border rounded-lg p-6 shadow-sm">
        <FormRenderer
          :doctype="dt"
          :model-value="form"
          :disabled="isSaving"
          :errors="validationErrors"
          :overrides="displayOverrides"
          :reqd-overrides="reqdOverrides"
          @update:model-value="onFormUpdate($event)"
        />
      </div>

      <!-- Activity log -->
      <div v-if="id" class="mt-4 bg-card border border-border rounded-lg overflow-hidden">
        <button
          type="button"
          class="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          @click="toggleLog"
        >
          <History class="size-4" />
          <span class="flex-1 text-left">Журнал активності</span>
          <ChevronDown
            class="size-4 transition-transform duration-200"
            :class="{ 'rotate-180': showLog }"
          />
        </button>
        <Transition name="log">
          <div v-if="showLog" class="border-t border-border px-5 py-3">
            <div v-if="logLoading" class="flex justify-center py-4">
              <Spinner size="sm" />
            </div>
            <div v-else-if="activityLog.length === 0" class="text-sm text-muted-foreground py-2">
              Записів немає
            </div>
            <ul v-else class="space-y-2">
              <li
                v-for="entry in activityLog"
                :key="entry.id"
                class="flex items-start gap-3 text-sm"
              >
                <span class="text-muted-foreground text-xs mt-0.5 whitespace-nowrap">
                  {{ entry.created_at ? new Date(entry.created_at).toLocaleString('uk-UA') : '—' }}
                </span>
                <span class="font-medium text-foreground">{{ entry.user }}</span>
                <span class="text-muted-foreground">{{ entry.action }}</span>
              </li>
            </ul>
          </div>
        </Transition>
      </div>
    </template>

    <!-- Delete confirmation -->
    <AlertDialog :open="showDeleteModal" @update:open="showDeleteModal = $event">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Видалити документ?</AlertDialogTitle>
          <AlertDialogDescription>Цю дію не можна скасувати.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="showDeleteModal = false">Скасувати</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90" @click="handleDelete">Видалити</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Unsaved leave confirmation -->
    <AlertDialog :open="showLeaveModal" @update:open="showLeaveModal = $event">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Є незбережені зміни</AlertDialogTitle>
          <AlertDialogDescription>Покинути сторінку без збереження?</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="showLeaveModal = false">Залишитись</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90" @click="confirmLeave">Покинути</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>

<style scoped>
.log-enter-active,
.log-leave-active {
  transition: opacity 200ms ease, max-height 200ms ease;
  overflow: hidden;
}
.log-enter-from,
.log-leave-to {
  opacity: 0;
  max-height: 0;
}
.log-enter-to,
.log-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>

<style>
@keyframes field-shake {
  0%, 100% { transform: translateX(0); }
  20%, 60% { transform: translateX(-4px); }
  40%, 80% { transform: translateX(4px); }
}
.field-shake {
  animation: field-shake 0.4s ease;
}
</style>
