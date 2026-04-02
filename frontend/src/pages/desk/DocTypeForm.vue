<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { usePresence } from '@/core/composables/usePresence'
import { useClientScripts } from '@/core/composables/useClientScripts'
import PresenceAvatars from '@/components/ui/PresenceAvatars.vue'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType, GruntDocument } from '@/types'
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
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
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
  Copy,
  Undo2,
  EllipsisVertical,
  ExternalLink,
  Settings2,
} from 'lucide-vue-next'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import WorkflowBar from '@/components/views/WorkflowBar.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'

interface ActivityEntry {
  id: string
  action: string
  user: string
  details: Record<string, unknown> | null
  created_at: string | null
}

const auth = useAuthStore()
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

  // Apply duplicated document data from history state
  if (!props.id && window.history.state?.duplicate) {
    try {
      const clone = JSON.parse(window.history.state.duplicate) as Record<string, unknown>
      Object.assign(form.value, clone)
    } catch { /* ignore malformed state */ }
  }

  // Apply initial data from history state (e.g. from Calendar quick-add)
  if (!props.id && window.history.state?.initial_data) {
    try {
      const initial = JSON.parse(window.history.state.initial_data) as Record<string, unknown>
      Object.assign(form.value, initial)
    } catch { /* ignore malformed state */ }
  }

  // Run client scripts on_load after DocType metadata is available
  await runScriptEvent('on_load')
})

// WebSocket real-time + presence
const wsUrl = computed(() => props.id ? `/api/v1/ws/${props.doctype}/${props.id}` : null)
const docWs = useWebSocket(wsUrl.value)
const { lastMessage } = docWs
const { users: presenceUsers, fieldLocks, focusField, blurField } = usePresence(docWs)

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
  if (valid === false) return

  await runScriptEvent('before_save')

  try {
    const saved = await save()
    toast.success('Збережено')
    runScriptEvent('after_save')
    dtStore.invalidate(props.doctype)
    queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
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
    queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
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

function handleDuplicate() {
  const clone = { ...form.value }
  delete clone.id
  delete clone.name
  delete clone.created_at
  delete clone.updated_at
  delete clone.owner
  delete clone.modified_by
  delete clone.workflow_state

  const path = props.workspace
    ? `/${props.workspace}/list/${props.doctype}/new`
    : `/${props.doctype}/new`

  allowLeave = true
  router.push({ path, state: { duplicate: JSON.stringify(clone) } })
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
  <div class="p-4 sm:p-6 lg:p-8 max-w-full xl:max-w-7xl">
    <!-- Document header card -->
    <div class="bg-card rounded-xl shadow-md ring-1 ring-border/60 mb-6">
      <!-- Top bar: breadcrumb + actions -->
      <div class="flex items-center justify-between gap-4 px-6 pt-5 pb-4">
        <div class="min-w-0">
          <nav class="flex items-center gap-1.5 text-sm mb-1">
            <button class="text-muted-foreground hover:text-primary transition-colors"
              @click="router.push(workspace ? `/${workspace}/list/${doctype}` : `/${doctype}`)">
              {{ dt?.label ?? doctype }}
            </button>
            <ChevronRight class="size-3.5 text-muted-foreground/40" />
          </nav>
          <div class="flex items-center gap-3">
            <h1 class="text-2xl font-bold text-foreground truncate">{{ docTitle }}</h1>
            <Badge v-if="isDirty" variant="outline" class="border-amber-400 text-amber-600 shrink-0">Не збережено
            </Badge>
            <PresenceAvatars :users="presenceUsers" />
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <!-- Client script buttons -->
          <Button v-for="btn in scriptButtons" :key="btn.label" :variant="(btn.variant as any) ?? 'outline'" size="sm"
            @click="btn.action">
            {{ btn.label }}
          </Button>

          <Button :disabled="isSaving" size="sm" @click="handleSave">
            <Loader2 v-if="isSaving" class="size-4 animate-spin mr-1.5" />
            Зберегти
          </Button>

          <!-- Context menu -->
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button variant="ghost" size="icon-sm" class="text-foreground">
                <EllipsisVertical class="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-48">
              <!-- Print submenu -->
              <DropdownMenuSub v-if="id">
                <DropdownMenuSubTrigger>
                  <Printer class="size-4 mr-2" />
                  Друкувати
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=xlsx&token=${auth.token}`">
                    <FileSpreadsheet class="size-4 mr-2" />
                    Excel (.xlsx)
                  </DropdownMenuItem>
                  <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=pdf&token=${auth.token}`">
                    <FileText class="size-4 mr-2" />
                    PDF
                  </DropdownMenuItem>
                  <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=html&token=${auth.token}`"
                    target="_blank">
                    <Globe class="size-4 mr-2" />
                    HTML
                  </DropdownMenuItem>
                </DropdownMenuSubContent>
              </DropdownMenuSub>

              <DropdownMenuItem v-if="id" as="a" :href="`/${props.workspace ?? ''}/list/${doctype}/${id}`"
                target="_blank">
                <ExternalLink class="size-4 mr-2" />
                Відкрити у новій вкладці
              </DropdownMenuItem>

              <DropdownMenuItem as="a" :href="`/${props.workspace ?? ''}/list/DocType/${doctype}`" target="_blank">
                <Settings2 class="size-4 mr-2" />
                Редагувати Доктайп
              </DropdownMenuItem>

              <DropdownMenuItem v-if="dt" as="a"
                :href="`/${props.workspace ?? 'grunt'}/list/PrintFormat?filter[doctype]=${doctype}`" target="_blank">
                <Printer class="size-4 mr-2" />
                Налаштувати друк
              </DropdownMenuItem>

              <DropdownMenuItem v-if="id" @click="handleDuplicate">
                <Copy class="size-4 mr-2" />
                Створити копію
              </DropdownMenuItem>

              <DropdownMenuItem v-if="id && isDirty" @click="router.go(0)">
                <Undo2 class="size-4 mr-2" />
                Скасувати зміни
              </DropdownMenuItem>

              <DropdownMenuItem v-if="id" @click="toggleLog">
                <History class="size-4 mr-2" />
                Журнал активності
              </DropdownMenuItem>

              <template v-if="id">
                <DropdownMenuSeparator />
                <DropdownMenuItem class="text-destructive focus:text-destructive" @click="showDeleteModal = true">
                  <Trash2 class="size-4 mr-2" />
                  Видалити
                </DropdownMenuItem>
              </template>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <!-- Workflow (inside the header card) -->
      <WorkflowBar v-if="!isLoading && dt && id && document && dt.workflow" :doctype="dt" :doc-id="id"
        :doc="document as Record<string, unknown>"
        @transitioned="queryClient.invalidateQueries({ queryKey: ['document', doctype, id] })" />
    </div>

    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-16">
      <Spinner size="lg" />
    </div>

    <template v-else>
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
        <!-- Left: Form + Activity log -->
        <div class="min-w-0">
          <!-- Form -->
          <div class="bg-card rounded-xl p-6 shadow-md ring-1 ring-border/60">
            <FormRenderer :doctype="dt" :model-value="form" :disabled="isSaving" :errors="validationErrors"
              :overrides="displayOverrides" :reqd-overrides="reqdOverrides"
              :field-locks="fieldLocks"
              @update:model-value="onFormUpdate($event)"
              @field-focus="focusField($event)"
              @field-blur="blurField($event)" />
          </div>

          <!-- Activity log -->
          <div v-if="id" class="mt-4 bg-card rounded-xl overflow-hidden shadow-sm ring-1 ring-border/60">
            <button type="button"
              class="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              @click="toggleLog">
              <History class="size-4" />
              <span class="flex-1 text-left">Журнал активності</span>
              <ChevronDown class="size-4 transition-transform duration-200" :class="{ 'rotate-180': showLog }" />
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
                  <li v-for="entry in activityLog" :key="entry.id" class="flex items-start gap-3 text-sm">
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
        </div>

        <!-- Right: Sidebar -->
        <DocSidebar v-if="id && document" :doctype="dt" :document="document as GruntDocument" :workspace="workspace"
          class="lg:sticky lg:top-6 lg:self-start" />
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
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            @click="handleDelete">Видалити</AlertDialogAction>
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
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            @click="confirmLeave">Покинути</AlertDialogAction>
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

  0%,
  100% {
    transform: translateX(0);
  }

  20%,
  60% {
    transform: translateX(-4px);
  }

  40%,
  80% {
    transform: translateX(4px);
  }
}

.field-shake {
  animation: field-shake 0.4s ease;
}
</style>
