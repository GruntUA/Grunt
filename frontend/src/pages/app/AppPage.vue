<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from '@/components/AppIcon.vue'
import {
  RefreshCw, LayoutDashboard, Pencil, Plus, Save, X,
  Calendar, Timer, Link2, Printer, GripVertical,
} from '@lucide/vue'
import { VueDraggable } from 'vue-draggable-plus'
import { docsApi } from '@/core/api/docs'
import { getPageData, getPageWidgetData } from '@/core/api/pages'
import { WIDGET_PERIOD_LOADER } from '@/core/widgetPeriod'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import WidgetConfigPanel from '@/components/dashboard/WidgetConfigPanel.vue'
import { getPaletteGroups, getWidgetDef, widgetColSpan } from '@/core/widgetRegistry'
import type { DashboardWidget } from '@/types'
import { useToast } from '@/core/composables/useToast'
import { setPageTitle } from '@/core/composables/usePageTitle'
import { useMasonryGrid } from '@/core/composables/useMasonryGrid'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { SidebarTrigger } from '@/components/ui/sidebar'
const props = defineProps<{
  workspaceName: string
  pageName: string
}>()

const toast = useToast()
const grid = ref<HTMLElement | null>(null)
useMasonryGrid(grid)
const { t } = useI18n()

interface PageDoc {
  id: string
  name: string
  label: string
  description?: string
  is_published: boolean
  widgets: DashboardWidget[]
}

// State

const page   = ref<PageDoc | null>(null)
const widgetData  = ref<Record<string, unknown>>({})
const loading     = ref(true)
const refreshing  = ref(false)
const editMode    = ref(false)
const saving      = ref(false)

const selectedWidgetId = ref<string | null>(null)

const selectedWidget = computed<DashboardWidget | null>(() =>
  page.value?.widgets.find(w => w.id === selectedWidgetId.value) ?? null
)

// Global date filter
const dateFrom = ref('')
const dateTo   = ref('')

// Auto-refresh
const autoRefreshInterval = ref<number>(0)
const autoRefreshTimer    = ref<ReturnType<typeof setInterval> | null>(null)

// Embed modal
const showEmbedModal = ref(false)
const embedUrl = computed(() => `${window.location.origin}/page/${props.pageName}`)

// Widget types palette

// Single source of truth - see @/core/widgetRegistry. Keeps this palette and
// WidgetConfigPanel's type switcher from drifting out of sync (they used to
// be two independently hand-maintained lists).
const WIDGET_GROUPS = getPaletteGroups()

// Data loading

async function loadData() {
  try {
    widgetData.value = await getPageData(props.pageName, {
      dateFrom: dateFrom.value || undefined,
      dateTo:   dateTo.value   || undefined,
    })
  } catch { /* silent */ }
}

provide(WIDGET_PERIOD_LOADER, (widget, period) => getPageWidgetData(props.pageName, widget.id, period, {
  dateFrom: dateFrom.value || undefined,
  dateTo:   dateTo.value   || undefined,
}))

async function load() {
  loading.value = true
  try {
    const doc = await docsApi.get('Page', props.pageName) as unknown as PageDoc
    page.value = { ...doc, widgets: doc.widgets ?? [] }
    setPageTitle(page.value.label || props.pageName)
    await loadData()
  } catch (error: unknown) {
    if ((error as { response?: { status?: number } })?.response?.status === 404) {
      page.value = null
    }
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (!page.value) return
  refreshing.value = true
  try { await loadData() } finally { refreshing.value = false }
}

// Auto-refresh

function startAutoRefresh(seconds: number) {
  stopAutoRefresh()
  if (seconds > 0) autoRefreshTimer.value = setInterval(refresh, seconds * 1000)
}
function stopAutoRefresh() {
  if (autoRefreshTimer.value) { clearInterval(autoRefreshTimer.value); autoRefreshTimer.value = null }
}
onUnmounted(stopAutoRefresh)

// Dashboard CRUD

async function createPage() {
  loading.value = true
  try {
    await docsApi.create('Page', {
      name: props.pageName,
      label: props.pageName,
      is_published: true,
      widgets: [],
    })
    await load()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: { message?: string }; detail?: string } } })
      ?.response?.data?.error?.message
      ?? (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? t('Could not create the page')
    toast.error(msg)
  } finally {
    loading.value = false
  }
}

async function savePage() {
  if (!page.value) return
  saving.value = true
  try {
    await docsApi.update('Page', page.value.name, { widgets: page.value.widgets })
    exitEdit()
    await load()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message ?? t('Save error')
    toast.error(msg)
  } finally {
    saving.value = false
  }
}

// Edit mode

function enterEdit() {
  editMode.value = true
  selectedWidgetId.value = null
}

function exitEdit() {
  editMode.value = false
  selectedWidgetId.value = null
}

function cancelEdit() {
  exitEdit()
  load()
}

// Widget management

function generateId() { return 'w-' + Math.random().toString(36).substring(2, 9) }

function addWidget(type: string) {
  if (!page.value) return
  const id = generateId()
  const newWidget: DashboardWidget = {
    id,
    widget_type: type,
    title: t(getWidgetDef(type)?.label ?? t('New')),
    cols: type === 'shortcut' || type === 'clock' ? 1 : type === 'gauge' ? 1 : 2,
    color: 'primary',
    ref_doctype: '',
    aggregation: 'count',
    field: '',
    period: '30d',
    filters: undefined,
    group_by: '',
    date_field: '',
    icon: '',
    link_type: null,
    description: null,
    min_value: type === 'gauge' ? 0 : undefined,
    max_value: type === 'gauge' ? 100 : undefined,
    content: type === 'shortcuts_grid' ? '[]' : null,
  }
  page.value.widgets.push(newWidget)
  selectedWidgetId.value = id
}

function selectWidget(widget: DashboardWidget) {
  selectedWidgetId.value = widget.id
}

function removeWidget(widget: DashboardWidget) {
  if (!page.value) return
  const idx = page.value.widgets.findIndex(w => w.id === widget.id)
  if (idx !== -1) page.value.widgets.splice(idx, 1)
  if (selectedWidgetId.value === widget.id) selectedWidgetId.value = null
}

function handleWidgetChange(updated: DashboardWidget) {
  if (!page.value) return
  const idx = page.value.widgets.findIndex(w => w.id === updated.id)
  if (idx !== -1) page.value.widgets[idx] = updated
}

function handleRemoveFromPanel() {
  const w = selectedWidget.value
  if (w) removeWidget(w)
}

// Embed

function copyEmbedUrl() {
  navigator.clipboard.writeText(embedUrl.value)
  toast.success(t('Link copied'))
}

onMounted(load)

const printPage = () => window.print()
</script>

<template>
<div>
  <!-- Normal view -->
  <div class="p-3 sm:p-6">
    <!-- Header: controls wrap under the title on narrow screens -->
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-4">
      <div class="flex items-center gap-2 min-w-0">
        <SidebarTrigger class="shrink-0 -ml-1.5 text-muted-foreground/80" />
        <LayoutDashboard class="w-5 h-5 text-muted-foreground" />
        <h1 class="text-lg font-semibold">{{ page?.label ?? pageName }}</h1>
        <p v-if="page?.description" class="hidden sm:block text-muted-foreground ml-2 truncate">{{ page.description }}</p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <!-- Date filter -->
        <div v-if="page && !editMode" class="flex w-full sm:w-auto items-center gap-1.5">
          <Calendar class="w-4 h-4 text-muted-foreground shrink-0" />
          <Input v-model="dateFrom" type="date" class="h-8 min-w-0 flex-1 sm:w-auto sm:flex-none" :aria-label="t('From')" @change="refresh" />
          <span class="text-muted-foreground">—</span>
          <Input v-model="dateTo" type="date" class="h-8 min-w-0 flex-1 sm:w-auto sm:flex-none" :aria-label="t('To')" @change="refresh" />
        </div>

        <!-- Auto-refresh -->
        <div v-if="page && !editMode" class="flex items-center gap-1.5">
          <Timer class="w-4 h-4 text-muted-foreground shrink-0" />
          <NativeSelect v-model.number="autoRefreshInterval" size="sm" :aria-label="t('Auto-refresh')"
            @change="startAutoRefresh(autoRefreshInterval)">
            <NativeSelectOption :value="0">{{ t('Auto') }}</NativeSelectOption>
            <NativeSelectOption :value="30">{{ t('30s') }}</NativeSelectOption>
            <NativeSelectOption :value="60">{{ t('1m') }}</NativeSelectOption>
            <NativeSelectOption :value="300">{{ t('5m') }}</NativeSelectOption>
            <NativeSelectOption :value="600">{{ t('10m') }}</NativeSelectOption>
          </NativeSelect>
        </div>

        <template v-if="!editMode">
          <Button variant="outline" size="sm" :aria-label="t('Configure')" @click="enterEdit">
            <Pencil /> <span class="hidden sm:inline">{{ t('Configure') }}</span>
          </Button>
          <Button variant="outline" size="sm" :aria-label="t('Refresh')" :disabled="refreshing || loading" @click="refresh">
            <RefreshCw :class="{ 'animate-spin': refreshing }" /> <span class="hidden sm:inline">{{ t('Refresh') }}</span>
          </Button>
          <Button v-if="page" variant="outline" size="icon-sm" :aria-label="t('Embed page')" @click="showEmbedModal = true">
            <Link2 />
          </Button>
          <Button v-if="page" variant="outline" size="icon-sm" :aria-label="t('Print')" @click="printPage">
            <Printer />
          </Button>
        </template>
      </div>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
      <Skeleton v-for="i in 6" :key="i" class="h-36" />
    </div>

    <!-- Empty: no page -->
    <Empty v-else-if="!page">
      <EmptyHeader>
        <EmptyMedia variant="icon"><LayoutDashboard /></EmptyMedia>
        <EmptyTitle>{{ t('The page has not been created yet') }}</EmptyTitle>
      </EmptyHeader>
      <EmptyContent>
        <Button @click="createPage"><Plus /> {{ t('Create page') }}</Button>
      </EmptyContent>
    </Empty>

    <!-- Empty: no widgets -->
    <Empty v-else-if="!editMode && (page?.widgets.length ?? 0) === 0">
      <EmptyHeader>
        <EmptyMedia variant="icon"><LayoutDashboard /></EmptyMedia>
        <EmptyTitle>{{ t('The page is empty') }}</EmptyTitle>
      </EmptyHeader>
      <EmptyContent>
        <Button @click="enterEdit"><Pencil /> {{ t('Configure') }}</Button>
      </EmptyContent>
    </Empty>

    <!-- Widgets grid (normal mode) -->
    <div v-else-if="!editMode && (page?.widgets.length ?? 0) > 0" ref="grid"
      class="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
      <WidgetCard
        v-for="w in page?.widgets ?? []"
        :key="w.id"
        :widget="w"
        :data="(widgetData[w.id] ?? null) as unknown"
        :loading="refreshing"
        :workspace-name="workspaceName"
      />
    </div>
  </div>

  <!-- Edit mode overlay -->
  <Teleport to="body">
    <div v-if="editMode" class="fixed inset-0 z-50 flex flex-col bg-background overflow-hidden">

      <!-- Edit header -->
      <div class="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-card shrink-0">
        <LayoutDashboard class="size-4 text-muted-foreground" />
        <span class="font-semibold">{{ page?.label ?? pageName }}</span>
        <Badge variant="outline">{{ t('Edit mode') }}</Badge>
        <div class="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" @click="cancelEdit">
            <X /> {{ t('Cancel') }}
          </Button>
          <Button size="sm" :disabled="saving" @click="savePage">
            <Spinner v-if="saving" /><Save v-else /> {{ t('Save') }}
          </Button>
        </div>
      </div>

      <!-- 3-column body -->
      <div class="flex flex-1 overflow-hidden">

        <!-- Left: widget palette -->
        <div class="w-52 shrink-0 border-r border-border bg-muted/20 overflow-y-auto">
          <div class="px-3 py-3">
            <p class="font-semibold uppercase tracking-widest text-muted-foreground mb-2 px-1">
              {{ t('Widget types') }}
            </p>
            <div v-for="group in WIDGET_GROUPS" :key="group.category" class="mb-3">
              <p class="text-muted-foreground/70 px-1 mb-1">{{ group.category }}</p>
              <div class="space-y-0.5">
                <Button
                  v-for="wt in group.widgets"
                  :key="wt.type"
                  variant="ghost"
                  class="w-full justify-start"
                  @click="addWidget(wt.type)"
                >
                  <AppIcon :icon="wt.icon" class="text-muted-foreground" />
                  {{ t(wt.label) }}
                  <Plus class="ml-auto text-muted-foreground opacity-0 group-hover/button:opacity-100" />
                </Button>
              </div>
            </div>
          </div>
        </div>

        <!-- Center: canvas -->
        <div
          class="flex-1 overflow-y-auto bg-muted/10 p-4"
          @click.self="selectedWidgetId = null"
        >
          <!-- Empty canvas hint -->
          <Empty v-if="page && page.widgets.length === 0" class="border">
            <EmptyHeader>
              <EmptyMedia variant="icon"><Plus /></EmptyMedia>
              <EmptyTitle>{{ t('Choose a widget type') }}</EmptyTitle>
              <EmptyDescription>{{ t('Click any type in the left panel — it will appear here') }}</EmptyDescription>
            </EmptyHeader>
          </Empty>

          <VueDraggable
            v-else-if="page"
            v-model="page.widgets"
            class="grid grid-cols-2 lg:grid-cols-4 gap-3 auto-rows-auto"
            handle=".drag-handle"
            ghost-class="opacity-40"
          >
            <div
              v-for="element in page.widgets"
              :key="element.id"
              :class="[
                widgetColSpan(element.cols),
                'relative min-w-0 rounded-lg border-2 transition-colors cursor-pointer group',
                selectedWidgetId === element.id
                  ? 'border-primary shadow-md'
                  : 'border-transparent hover:border-primary/30',
              ]"
              @click.stop="selectWidget(element)"
            >
              <!-- Drag handle -->
              <div class="absolute top-1.5 left-1.5 z-10 drag-handle cursor-grab opacity-0 group-hover:opacity-60 transition-opacity p-0.5 rounded bg-background/80">
                <GripVertical class="size-3.5 text-muted-foreground" />
              </div>
              <!-- Remove button -->
              <Button
                variant="destructive"
                size="icon-xs"
                class="absolute top-1.5 right-1.5 z-10 opacity-0 group-hover:opacity-100"
                :aria-label="t('Remove')"
                @click.stop="removeWidget(element)"
              >
                <X />
              </Button>
              <!-- Widget preview -->
              <WidgetCard
                :widget="element"
                :data="(widgetData[element.id] ?? null) as unknown"
                :workspace-name="workspaceName"
              />
            </div>
          </VueDraggable>
        </div>

        <!-- Right: config panel -->
        <div class="w-72 shrink-0 border-l border-border bg-card overflow-hidden flex flex-col">
          <WidgetConfigPanel
            :widget="selectedWidget"
            @change="handleWidgetChange"
            @remove="handleRemoveFromPanel"
          />
        </div>

      </div>
    </div>
  </Teleport>

  <!-- Embed dialog -->
  <Dialog v-model:open="showEmbedModal">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ t('Embed page') }}</DialogTitle>
      </DialogHeader>
      <FieldGroup>
        <Field>
          <FieldLabel for="embed-url">{{ t('Direct link') }}</FieldLabel>
          <div class="flex gap-2">
            <Input id="embed-url" :model-value="embedUrl" readonly class="font-mono" />
            <Button variant="outline" @click="copyEmbedUrl">{{ t('Copy') }}</Button>
          </div>
        </Field>
        <Field>
          <FieldLabel for="embed-iframe">iframe</FieldLabel>
          <Textarea
            id="embed-iframe"
            :model-value="`<iframe src=&quot;${embedUrl}&quot; width=&quot;100%&quot; height=&quot;600&quot; frameborder=&quot;0&quot;></iframe>`"
            readonly rows="3"
            class="font-mono field-sizing-fixed"
          />
        </Field>
      </FieldGroup>
    </DialogContent>
  </Dialog>
</div>
</template>
