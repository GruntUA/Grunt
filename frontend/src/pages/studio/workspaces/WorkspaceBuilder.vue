<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { workspaceApi } from '@/core/api/workspace'
import type { Workspace } from '@/core/api/workspace'
import { useDocTypeStore } from '@/stores/doctype'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FormField } from '@/components/ui/form-field'
import { Spinner } from '@/components/ui/spinner'
import { Loader2 } from 'lucide-vue-next'

const dtStore = useDocTypeStore()
const toast = useToast()

const workspaces = ref<Workspace[]>([])
const selected = ref<Workspace | null>(null)
const editForm = ref<Workspace | null>(null)
const loading = ref(false)
const saving = ref(false)

onMounted(async () => {
  loading.value = true
  await dtStore.loadAll()
  try {
    workspaces.value = await workspaceApi.list()
  } finally {
    loading.value = false
  }
})

function selectWorkspace(ws: Workspace) {
  selected.value = ws
  editForm.value = JSON.parse(JSON.stringify(ws))
}

async function save() {
  if (!editForm.value || !selected.value) return
  saving.value = true
  try {
    const updated = await workspaceApi.update(selected.value.name, editForm.value)
    // Update in list
    const idx = workspaces.value.findIndex(w => w.name === selected.value!.name)
    if (idx >= 0) workspaces.value[idx] = updated
    selected.value = updated
    editForm.value = JSON.parse(JSON.stringify(updated))
    toast.success('Workspace збережено')
  } catch {
    toast.error('Помилка збереження')
  } finally {
    saving.value = false
  }
}

async function createNew() {
  const name = prompt('Slug нового workspace (латиниця, без пробілів):')
  if (!name) return
  try {
    const ws = await workspaceApi.create({
      name,
      label: name.charAt(0).toUpperCase() + name.slice(1),
      icon: '📁',
      color: '#2D6A4F',
      items: [],
    })
    workspaces.value.push(ws)
    selectWorkspace(ws)
    toast.success('Workspace створено')
  } catch {
    toast.error('Помилка створення')
  }
}

async function deleteSelected() {
  if (!selected.value) return
  if (!confirm(`Видалити workspace "${selected.value.label}"?`)) return
  try {
    await workspaceApi.delete(selected.value.name)
    workspaces.value = workspaces.value.filter(w => w.name !== selected.value!.name)
    selected.value = null
    editForm.value = null
    toast.success('Workspace видалено')
  } catch {
    toast.error('Помилка видалення')
  }
}

// Items editing
function addItem() {
  if (!editForm.value) return
  editForm.value.items.push({
    section: '',
    type: 'DocType',
    label: '',
    icon: '',
    link_to: '',
    show_count: false,
    count_filters: '',
    show_new_btn: false,
    roles: '',
    sequence: editForm.value.items.length,
  })
}

function addSection() {
  if (!editForm.value) return
  editForm.value.items.push({
    section: 'Нова секція',
    type: 'DocType',
    label: '',
    icon: '',
    link_to: '',
    show_count: false,
    count_filters: '',
    show_new_btn: false,
    roles: '',
    sequence: editForm.value.items.length,
  })
}

function addDivider() {
  if (!editForm.value) return
  editForm.value.items.push({
    section: '',
    type: 'Divider',
    label: '',
    icon: '',
    link_to: '',
    show_count: false,
    count_filters: '',
    show_new_btn: false,
    roles: '',
    sequence: editForm.value.items.length,
  })
}

function removeItem(index: number) {
  if (!editForm.value) return
  editForm.value.items.splice(index, 1)
  resequence()
}

function moveItem(from: number, direction: -1 | 1) {
  if (!editForm.value) return
  const to = from + direction
  if (to < 0 || to >= editForm.value.items.length) return
  const items = editForm.value.items
  ;[items[from], items[to]] = [items[to], items[from]]
  resequence()
}

function resequence() {
  if (!editForm.value) return
  editForm.value.items.forEach((item, i) => { item.sequence = i })
}

const activeTab = ref<'general' | 'navigation'>('navigation')

const doctypeOptions = computed(() =>
  dtStore.doctypes.map(dt => ({ value: dt.name, label: dt.label }))
)
</script>

<template>
  <div class="p-8">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-foreground">Воркспейси</h1>
      <Button @click="createNew">+ Новий</Button>
    </div>

    <div v-if="loading" class="flex justify-center py-16"><Spinner size="lg" /></div>

    <div v-else class="flex gap-6">
      <!-- Left: workspace list -->
      <div class="w-72 shrink-0 space-y-1">
        <div
          v-for="ws in workspaces"
          :key="ws.name"
          class="flex items-center gap-3 px-3 py-2.5 rounded-md cursor-pointer transition-colors"
          :class="selected?.name === ws.name ? 'bg-accent border border-primary/20' : 'bg-card border border-border hover:border-primary'"
          @click="selectWorkspace(ws)"
        >
          <span class="w-3 h-8 rounded-sm shrink-0" :style="{ backgroundColor: ws.color }" />
          <span class="text-base">{{ ws.icon }}</span>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-foreground truncate">{{ ws.label }}</p>
            <p class="text-xs text-muted-foreground/70">{{ ws.name }}</p>
          </div>
        </div>
      </div>

      <!-- Right: editor -->
      <div v-if="editForm" class="flex-1 min-w-0">
        <!-- Tabs -->
        <div class="flex gap-1 mb-4 border-b border-border">
          <button
            class="px-4 py-2 text-sm font-medium transition-colors"
            :class="activeTab === 'general' ? 'text-primary border-b-2 border-primary' : 'text-muted-foreground'"
            @click="activeTab = 'general'"
          >Загальне</button>
          <button
            class="px-4 py-2 text-sm font-medium transition-colors"
            :class="activeTab === 'navigation' ? 'text-primary border-b-2 border-primary' : 'text-muted-foreground'"
            @click="activeTab = 'navigation'"
          >Навігація</button>
        </div>

        <!-- General tab -->
        <div v-if="activeTab === 'general'" class="space-y-4 max-w-lg">
          <FormField label="Назва">
            <template #default="{ id }">
              <Input :id="id" v-model="editForm.label" />
            </template>
          </FormField>
          <div class="flex gap-4">
            <div class="flex-1">
              <label class="block text-sm font-medium text-foreground mb-1">Іконка (emoji)</label>
              <input v-model="editForm.icon" class="w-full px-3 py-2 text-lg border border-border rounded-sm focus:outline-none focus:border-primary" />
            </div>
            <div class="flex-1">
              <label class="block text-sm font-medium text-foreground mb-1">Колір</label>
              <input v-model="editForm.color" type="color" class="w-full h-10 border border-border rounded-sm cursor-pointer" />
            </div>
          </div>
          <FormField label="Опис">
            <template #default="{ id }">
              <Input :id="id" v-model="editForm.description" />
            </template>
          </FormField>
          <FormField label="Ролі (через кому)">
            <template #default="{ id }">
              <Input :id="id" v-model="editForm.roles" placeholder="Role1,Role2" />
            </template>
          </FormField>
          <div class="flex items-center gap-2">
            <input v-model="editForm.is_hidden" type="checkbox" class="rounded" id="ws-hidden" />
            <label for="ws-hidden" class="text-sm text-muted-foreground">Приховано з Desk</label>
          </div>
        </div>

        <!-- Navigation tab -->
        <div v-if="activeTab === 'navigation'" class="flex gap-4">
          <!-- Items editor -->
          <div class="flex-1 min-w-0">
            <div class="flex gap-2 mb-3">
              <Button variant="secondary" size="sm" @click="addItem">+ Пункт</Button>
              <Button variant="secondary" size="sm" @click="addSection">+ Секція</Button>
              <Button variant="secondary" size="sm" @click="addDivider">Розділювач</Button>
            </div>

            <div class="space-y-1">
              <div
                v-for="(item, i) in editForm.items"
                :key="i"
                class="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-sm text-sm"
              >
                <!-- Reorder -->
                <div class="flex flex-col gap-0.5 shrink-0">
                  <button class="text-xs text-muted-foreground/70 hover:text-foreground" @click="moveItem(i, -1)">▲</button>
                  <button class="text-xs text-muted-foreground/70 hover:text-foreground" @click="moveItem(i, 1)">▼</button>
                </div>

                <template v-if="item.type === 'Divider'">
                  <hr class="flex-1 border-border" />
                  <span class="text-xs text-muted-foreground/70">Розділювач</span>
                </template>

                <template v-else>
                  <!-- Icon -->
                  <input v-model="item.icon" class="w-8 text-center border-0 bg-transparent text-base" placeholder="📋" />

                  <!-- Section (if first in group) -->
                  <input v-model="item.section" class="w-24 px-1 py-0.5 text-xs border border-border rounded bg-background shrink-0" placeholder="Секція" />

                  <!-- Label -->
                  <input v-model="item.label" class="flex-1 min-w-0 px-1 py-0.5 border border-border rounded" placeholder="Назва" />

                  <!-- Type badge -->
                  <select v-model="item.type" class="text-xs px-1 py-0.5 border border-border rounded bg-background shrink-0">
                    <option value="DocType">DocType</option>
                    <option value="Report">Report</option>
                    <option value="URL">URL</option>
                    <option value="Dashboard">Dashboard</option>
                  </select>

                  <!-- Link to -->
                  <select
                    v-if="item.type === 'DocType'"
                    v-model="item.link_to"
                    class="w-32 text-xs px-1 py-0.5 border border-border rounded shrink-0"
                  >
                    <option value="">—</option>
                    <option v-for="opt in doctypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                  <input v-else v-model="item.link_to" class="w-32 text-xs px-1 py-0.5 border border-border rounded shrink-0" placeholder="link_to" />

                  <!-- Count checkbox -->
                  <label class="flex items-center gap-0.5 text-xs text-muted-foreground/70 shrink-0" title="Показати лічильник">
                    <input v-model="item.show_count" type="checkbox" class="rounded" />
                    #
                  </label>
                </template>

                <!-- Delete -->
                <button class="text-muted-foreground/70 hover:text-destructive text-sm shrink-0" @click="removeItem(i)">×</button>
              </div>
            </div>
          </div>

          <!-- Live preview -->
          <div class="w-64 shrink-0 border border-border rounded-lg overflow-hidden bg-sidebar h-fit">
            <div class="px-3 py-2 border-b border-sidebar-border text-xs font-medium text-muted-foreground/70 uppercase">Preview</div>
            <div class="py-2">
              <div class="px-3 py-1.5 flex items-center gap-2 text-sm">
                <span>{{ editForm.icon }}</span>
                <span class="font-semibold text-foreground">{{ editForm.label }}</span>
              </div>
              <template v-for="(item, i) in editForm.items" :key="i">
                <hr v-if="item.type === 'Divider'" class="border-sidebar-border my-1 mx-3" />
                <template v-else>
                  <p v-if="item.section" class="px-3 pt-3 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground">{{ item.section }}</p>
                  <div class="flex items-center gap-2 px-3 py-1.5 text-sm text-muted-foreground">
                    <span class="text-xs">{{ item.icon }}</span>
                    <span class="truncate">{{ item.label || item.link_to || '...' }}</span>
                  </div>
                </template>
              </template>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex gap-2 mt-6 pt-4 border-t border-border">
          <Button :disabled="saving" @click="save"><Loader2 v-if="saving" class="size-4 animate-spin" />Зберегти</Button>
          <Button variant="destructive" @click="deleteSelected">Видалити</Button>
        </div>
      </div>

      <!-- No selection -->
      <div v-else class="flex-1 flex items-center justify-center text-sm text-muted-foreground/70">
        Оберіть workspace зліва або створіть новий
      </div>
    </div>
  </div>
</template>
