<script setup lang="ts">
import { ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import draggable from 'vuedraggable'
import { workspaceApi, type Workspace, type WorkspaceLink, type SearchResult } from '@/core/api/workspace'
import { docsApi } from '@/core/api/docs'
import type { GruntDocument } from '@/types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import {
  GripVertical,
  Plus,
  Trash2,
  Search,
  Settings2,
  LayoutDashboard,
  Loader2,
} from '@lucide/vue'
import { useToast } from '@/core/composables/useToast'

const props = defineProps<{
  open: boolean
  workspace: Workspace
}>()

const emit = defineEmits<{
  (e: 'update:open', val: boolean): void
  (e: 'saved'): void
}>()

const toast = useToast()
const items = ref<WorkspaceLink[]>([])
const isSaving = ref(false)

type ActivePanel = null | 'doctype' | 'dashboard'
const activePanel = ref<ActivePanel>(null)

// DocType/Report search
const searchQuery = ref('')
const searchResults = ref<SearchResult[]>([])
const isSearching = ref(false)

// Dashboard panel
const dashboardQuery = ref('')
const dashboardResults = ref<GruntDocument[]>([])
const isDashboardSearching = ref(false)
const showCreateForm = ref(false)
const newDashboardLabel = ref('')
const newDashboardSlug = ref('')
const isCreatingDashboard = ref(false)

watch(() => props.open, (newVal) => {
  if (newVal) {
    items.value = props.workspace.items.map((it, idx) => ({ ...it, sequence: it.sequence ?? idx }))
      .sort((a, b) => a.sequence - b.sequence)
  } else {
    activePanel.value = null
    dashboardQuery.value = ''
    dashboardResults.value = []
    newDashboardLabel.value = ''
    newDashboardSlug.value = ''
    showCreateForm.value = false
  }
})

// ── DocType/Report search ─────────────────────────────────────────────────

async function performSearch() {
  if (searchQuery.value.length < 2) {
    searchResults.value = []
    return
  }
  isSearching.value = true
  try {
    searchResults.value = await workspaceApi.search(searchQuery.value)
  } catch {
    searchResults.value = []
  } finally {
    isSearching.value = false
  }
}

function addItem(res: SearchResult) {
  const newItem: WorkspaceLink = {
    section: '',
    type: res.doctype === 'Report' ? 'Report' : 'DocType',
    label: res.display_title || res.name,
    icon: '📄',
    link_to: res.name,
    show_count: false,
    show_new_btn: true,
    roles: '',
    sequence: items.value.length,
  }
  items.value = [...items.value, newItem]
  activePanel.value = null
  searchQuery.value = ''
  searchResults.value = []
}

function addDivider() {
  items.value = [...items.value, {
    section: '__divider__',
    type: 'Divider',
    label: '',
    icon: '',
    link_to: '',
    show_count: false,
    show_new_btn: false,
    roles: '',
    sequence: items.value.length,
  }]
}

// ── Dashboard panel ───────────────────────────────────────────────────────

const UA_MAP: Record<string, string> = {
  'а':'a','б':'b','в':'v','г':'h','ґ':'g','д':'d','е':'e','є':'ye',
  'ж':'zh','з':'z','и':'y','і':'i','ї':'yi','й':'y','к':'k','л':'l',
  'м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u',
  'ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ь':'',
  'ю':'yu','я':'ya',
}

function slugify(label: string): string {
  return label
    .toLowerCase()
    .split('')
    .map(c => UA_MAP[c] ?? c)
    .join('')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
}

function onNewLabelInput() {
  newDashboardSlug.value = slugify(newDashboardLabel.value)
}

async function searchDashboards() {
  isDashboardSearching.value = true
  try {
    const res = await docsApi.list('Dashboard', {
      search: dashboardQuery.value || undefined,
      per_page: 20,
    })
    dashboardResults.value = res.data
  } catch {
    dashboardResults.value = []
  } finally {
    isDashboardSearching.value = false
  }
}

function openDashboardPanel() {
  if (activePanel.value === 'dashboard') {
    activePanel.value = null
    return
  }
  activePanel.value = 'dashboard'
  showCreateForm.value = false
  dashboardQuery.value = ''
  searchDashboards()
}

function addDashboardItem(doc: GruntDocument) {
  if (items.value.some(i => i.type === 'Dashboard' && i.link_to === doc.name)) {
    toast.info('Цей дашборд вже є в меню')
    return
  }
  items.value.push({
    section: '',
    type: 'Dashboard',
    label: String(doc.label ?? doc.name),
    icon: '📊',
    link_to: doc.name,
    show_count: false,
    show_new_btn: false,
    roles: '',
    sequence: items.value.length,
  })
  activePanel.value = null
}

async function createDashboard() {
  const label = newDashboardLabel.value.trim()
  if (!label) return
  const name = newDashboardSlug.value || slugify(label)
  if (!name) {
    toast.error('Не вдалося сформувати ідентифікатор')
    return
  }
  isCreatingDashboard.value = true
  try {
    const created = await docsApi.create('Dashboard', {
      name,
      label,
      workspace: props.workspace.name,
      is_published: true,
      widgets: [],
    })
    items.value.push({
      section: '',
      type: 'Dashboard',
      label,
      icon: '📊',
      link_to: created.name,
      show_count: false,
      show_new_btn: false,
      roles: '',
      sequence: items.value.length,
    })
    toast.success(`Дашборд "${label}" створено`)
    activePanel.value = null
    newDashboardLabel.value = ''
    newDashboardSlug.value = ''
    showCreateForm.value = false
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message
    toast.error(msg ?? 'Помилка створення дашборду')
  } finally {
    isCreatingDashboard.value = false
  }
}

// ── Common ────────────────────────────────────────────────────────────────

function removeItem(idx: number) {
  items.value.splice(idx, 1)
}

const expandedIdx = ref<number | null>(null)

function toggleExpand(idx: number) {
  expandedIdx.value = expandedIdx.value === idx ? null : idx
}

async function save() {
  isSaving.value = true
  try {
    const updatedItems = items.value.map((it, idx) => ({ ...it, sequence: idx }))
    await workspaceApi.update(props.workspace.name, {
      ...props.workspace,
      items: updatedItems,
    })
    toast.success('Налаштування збережено')
    emit('saved')
    emit('update:open', false)
  } catch {
    toast.error('Помилка збереження')
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <Dialog :visible="open" modal
    :pt="{ root: { class: 'max-w-2xl h-[80vh] flex flex-col' }, content: { class: 'p-0 flex-1 flex flex-col overflow-hidden' } }"
    @update:visible="$emit('update:open', $event)">
    <template #header>
      <span class="font-semibold">Налаштування бічного меню: {{ workspace.label }}</span>
    </template>
    <ScrollPanel class="flex-1 px-6 py-4">
        <div class="space-y-4">
          <!-- Toolbar -->
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-medium">Пункти меню</h3>
            <div class="flex gap-2">
              <Button outlined size="small"
                :class="activePanel === 'doctype' ? 'border-primary text-primary bg-primary/5' : ''"
                @click="activePanel = activePanel === 'doctype' ? null : 'doctype'"
              >
                <Plus class="size-4 mr-1.5" />
                Додати пункт
              </Button>
              <Button outlined size="small"
                :class="activePanel === 'dashboard' ? 'border-primary text-primary bg-primary/5' : ''"
                @click="openDashboardPanel"
              >
                <LayoutDashboard class="size-4 mr-1.5" />
                Дашборд
              </Button>
              <Button outlined size="small" @click="addDivider">
                Розділювач
              </Button>
            </div>
          </div>

          <!-- DocType/Report search panel -->
          <div v-if="activePanel === 'doctype'" class="bg-accent/50 p-3 rounded-lg border border-border space-y-3">
            <div class="relative">
              <Search class="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                v-model="searchQuery"
                placeholder="Пошук DocType, Звіту..."
                class="pl-9"
                @input="performSearch"
              />
            </div>
            <div v-if="searchResults.length > 0" class="bg-card border rounded-md divide-y overflow-hidden max-h-48 overflow-y-auto">
              <button
                v-for="res in searchResults"
                :key="res.id"
                type="button"
                class="w-full px-3 py-2 text-sm text-left hover:bg-accent transition-colors flex items-center justify-between"
                @click="addItem(res)"
              >
                <span>{{ res.display_title || res.name }} <span class="text-xs text-muted-foreground ml-1">({{ res.doctype }})</span></span>
                <Plus class="size-3.5" />
              </button>
            </div>
            <div v-else-if="searchQuery.length >= 2 && !isSearching" class="text-xs text-muted-foreground text-center py-2">
              Нічого не знайдено
            </div>
          </div>

          <!-- Dashboard panel -->
          <div v-if="activePanel === 'dashboard'" class="bg-accent/50 p-3 rounded-lg border border-border space-y-3">
            <!-- Mode toggle -->
            <div class="flex gap-2">
              <Button size="small"
                :variant="!showCreateForm ? 'default' : 'outline'"
                @click="showCreateForm = false"
              >
                Вибрати існуючий
              </Button>
              <Button size="small"
                :variant="showCreateForm ? 'default' : 'outline'"
                @click="showCreateForm = true"
              >
                Створити новий
              </Button>
            </div>

            <!-- Search existing dashboards -->
            <template v-if="!showCreateForm">
              <div class="relative">
                <Search class="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                <Input
                  v-model="dashboardQuery"
                  placeholder="Пошук дашборду..."
                  class="pl-9"
                  @input="searchDashboards"
                />
              </div>
              <div v-if="isDashboardSearching" class="flex justify-center py-2">
                <Loader2 class="size-4 animate-spin text-muted-foreground" />
              </div>
              <div v-else-if="dashboardResults.length > 0" class="bg-card border rounded-md divide-y overflow-hidden max-h-48 overflow-y-auto">
                <button
                  v-for="doc in dashboardResults"
                  :key="doc.id"
                  type="button"
                  class="w-full px-3 py-2 text-sm text-left hover:bg-accent transition-colors flex items-center justify-between"
                  @click="addDashboardItem(doc)"
                >
                  <span class="flex items-center gap-2">
                    <LayoutDashboard class="size-3.5 text-muted-foreground shrink-0" />
                    {{ doc.label ?? doc.name }}
                  </span>
                  <Plus class="size-3.5 shrink-0" />
                </button>
              </div>
              <div v-else-if="!isDashboardSearching" class="text-xs text-muted-foreground text-center py-2">
                Дашборди не знайдено
              </div>
            </template>

            <!-- Create new dashboard -->
            <template v-else>
              <div class="space-y-3">
                <div class="space-y-1.5">
                  <Label>Назва дашборду</Label>
                  <Input
                    v-model="newDashboardLabel"
                    placeholder="напр. Аналітика продажів"
                    @input="onNewLabelInput"
                  />
                </div>
                <div class="space-y-1.5">
                  <Label class="text-xs text-muted-foreground">Ідентифікатор (URL)</Label>
                  <Input
                    v-model="newDashboardSlug"
                    placeholder="analityka-prodazhiv"
                    class="font-mono text-xs"
                  />
                  <p class="text-[11px] text-muted-foreground">Генерується автоматично. Можна змінити вручну.</p>
                </div>
                <Button
                  class="w-full"
                  :disabled="isCreatingDashboard || !newDashboardLabel.trim()"
                  @click="createDashboard"
                >
                  <Loader2 v-if="isCreatingDashboard" class="size-4 mr-1.5 animate-spin" />
                  <Plus v-else class="size-4 mr-1.5" />
                  Створити і додати до меню
                </Button>
              </div>
            </template>
          </div>

          <!-- Items list -->
          <draggable
            v-model="items"
            item-key="link_to"
            handle=".drag-handle"
            class="space-y-2"
            ghost-class="opacity-50"
          >
            <template #item="{ element, index }">
              <div class="group bg-card border rounded-lg overflow-hidden transition-all shadow-sm">
                <div class="flex items-center h-11 px-3 gap-3">
                  <div class="drag-handle cursor-grab active:cursor-grabbing p-1 hover:bg-accent rounded text-muted-foreground">
                    <GripVertical class="size-4" />
                  </div>
                  <div class="flex-1 flex items-center gap-2 min-w-0">
                    <AppIcon v-if="element.type !== 'Divider'" :icon="element.icon || 'file'" class="size-4 shrink-0 text-muted-foreground" />
                    <span v-if="element.type === 'Divider'" class="h-px bg-border flex-1 mx-2"></span>
                    <span v-else class="text-sm font-medium truncate">{{ element.label || element.link_to }}</span>
                    <span v-if="element.section" class="text-[10px] bg-muted px-1.5 py-0.5 rounded text-muted-foreground uppercase shrink-0">{{ element.section }}</span>
                    <span v-if="element.type === 'Dashboard'" class="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded shrink-0">Dashboard</span>
                  </div>
                  <div class="flex items-center gap-1">
                    <Button text class="opacity-0 group-hover:opacity-100" @click="toggleExpand(index)">
                      <Settings2 class="size-4" />
                    </Button>
                    <Button text class="text-destructive opacity-0 group-hover:opacity-100" @click="removeItem(index)">
                      <Trash2 class="size-4" />
                    </Button>
                  </div>
                </div>

                <!-- Expanded edit panel -->
                <div v-if="expandedIdx === index" class="border-t bg-muted/30 p-4 space-y-4">
                  <div v-if="element.type !== 'Divider'" class="grid grid-cols-2 gap-4">
                    <div class="space-y-2">
                      <Label>Назва</Label>
                      <Input v-model="element.label" />
                    </div>
                    <div class="space-y-2">
                      <Label>Секція (група)</Label>
                      <Input v-model="element.section" placeholder="напр. Налаштування" />
                    </div>
                    <div class="space-y-2">
                      <Label>Іконка</Label>
                      <Input v-model="element.icon" />
                    </div>
                    <div class="space-y-2">
                      <Label>Перехід до</Label>
                      <Input v-model="element.link_to" :disabled="element.type === 'Dashboard'" />
                    </div>
                  </div>

                  <div v-if="element.type === 'DocType'" class="flex flex-wrap gap-6 pt-2">
                    <div class="flex items-center space-x-2">
                      <Checkbox binary :id="'sc-' + index" :model-value="element.show_count" @update:model-value="element.show_count = $event" />
                      <Label :for="'sc-' + index" class="text-xs font-normal">Показувати лічильник</Label>
                    </div>
                    <div class="flex items-center space-x-2">
                      <Checkbox binary :id="'sn-' + index" :model-value="element.show_new_btn" @update:model-value="element.show_new_btn = $event" />
                      <Label :for="'sn-' + index" class="text-xs font-normal">Кнопка "Створити"</Label>
                    </div>
                  </div>

                  <div v-if="element.type !== 'Divider'" class="space-y-2">
                    <Label class="text-xs">Ролі (через кому, порожньо — всім)</Label>
                    <Input v-model="element.roles" placeholder="System Manager, HR User" />
                  </div>
                </div>
              </div>
            </template>
          </draggable>

          <div v-if="items.length === 0" class="text-center py-12 border-2 border-dashed rounded-xl text-muted-foreground">
            Меню порожнє. Додайте перший пункт.
          </div>
        </div>
      </ScrollPanel>

    <template #footer>
      <Button text @click="$emit('update:open', false)">Скасувати</Button>
      <Button :disabled="isSaving" @click="save">
        <Plus v-if="!isSaving" class="size-4 mr-1.5" />
        Зберегти зміни
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.drag-handle {
  touch-action: none;
}
</style>
