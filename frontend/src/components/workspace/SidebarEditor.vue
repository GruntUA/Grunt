<script setup lang="ts">
import { ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { workspaceApi, type Workspace, type WorkspaceLink, type SearchResult } from '@/core/api/workspace'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  GripVertical,
  Plus,
  Trash2,
  Search,
  Settings2,
  ChevronDown,
  ChevronUp,
} from 'lucide-vue-next'
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

// Search for adding items
const searchQuery = ref('')
const searchResults = ref<SearchResult[]>([])
const isSearching = ref(false)
const showSearch = ref(false)

watch(() => props.open, (newVal) => {
  if (newVal) {
    // Clone items and ensure they have sequence
    items.value = props.workspace.items.map((it, idx) => ({ ...it, sequence: it.sequence ?? idx }))
      .sort((a, b) => a.sequence - b.sequence)
  }
})

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
    type: 'DocType', // Default, we might want to detect if it's a Report
    label: res.display_title || res.name,
    icon: '📄',
    link_to: res.name,
    show_count: false,
    show_new_btn: true,
    roles: '',
    sequence: items.value.length,
  }
  
  // Basic heuristic: if it's from DocType list, it's a DocType. 
  // Wait, the search API returns results. If it's a Report, the search result might indicate it.
  if (res.doctype === 'Report') newItem.type = 'Report'

  items.value.push(newItem)
  showSearch.value = false
  searchQuery.value = ''
  searchResults.value = []
}

function addDivider() {
  items.value.push({
    section: '__divider__',
    type: 'Divider',
    label: '',
    icon: '',
    link_to: '',
    show_count: false,
    show_new_btn: false,
    roles: '',
    sequence: items.value.length,
  })
}

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
    // Update sequences based on current order
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
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogContent class="max-w-2xl h-[80vh] flex flex-col p-0">
      <DialogHeader class="px-6 py-4 border-b">
        <DialogTitle>Налаштування бічного меню: {{ workspace.label }}</DialogTitle>
      </DialogHeader>

      <ScrollArea class="flex-1 px-6 py-4">
        <div class="space-y-4">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-medium">Пункти меню</h3>
            <div class="flex gap-2">
              <Button variant="outline" size="sm" @click="showSearch = !showSearch">
                <Plus class="size-4 mr-1.5" />
                Додати пункт
              </Button>
              <Button variant="outline" size="sm" @click="addDivider">
                Розділювач
              </Button>
            </div>
          </div>

          <!-- Quick Add Search -->
          <div v-if="showSearch" class="bg-accent/50 p-3 rounded-lg border border-border space-y-3">
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

          <draggable
            v-model="items"
            item-key="link_to"
            handle=".drag-handle"
            class="space-y-2"
            ghost-class="opacity-50"
          >
            <template #item="{ element, index }">
              <div class="group bg-card border rounded-lg overflow-hidden transition-all shadow-sm">
                <!-- Collapsed View / Handle -->
                <div class="flex items-center h-11 px-3 gap-3">
                  <div class="drag-handle cursor-grab active:cursor-grabbing p-1 hover:bg-accent rounded text-muted-foreground">
                    <GripVertical class="size-4" />
                  </div>
                  
                  <div class="flex-1 flex items-center gap-2 min-w-0">
                    <span v-if="element.type !== 'Divider'" class="text-base shrink-0">{{ element.icon || '📄' }}</span>
                    <span v-if="element.type === 'Divider'" class="h-px bg-border flex-1 mx-2"></span>
                    <span v-else class="text-sm font-medium truncate">{{ element.label || element.link_to }}</span>
                    <span v-if="element.section" class="text-[10px] bg-muted px-1.5 py-0.5 rounded text-muted-foreground uppercase">{{ element.section }}</span>
                  </div>

                  <div class="flex items-center gap-1">
                    <Button variant="ghost" size="icon-sm" class="opacity-0 group-hover:opacity-100" @click="toggleExpand(index)">
                      <Settings2 class="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon-sm" class="text-destructive opacity-0 group-hover:opacity-100" @click="removeItem(index)">
                      <Trash2 class="size-4" />
                    </Button>
                  </div>
                </div>

                <!-- Expanded Edit Panel -->
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
                      <Label>Іконка (Emoji або Lucide)</Label>
                      <Input v-model="element.icon" />
                    </div>
                    <div class="space-y-2">
                      <Label>Перехід до</Label>
                      <Input v-model="element.link_to" />
                    </div>
                  </div>

                  <div v-if="element.type !== 'Divider'" class="flex flex-wrap gap-6 pt-2">
                    <div class="flex items-center space-x-2">
                      <Checkbox :id="'sc-' + index" :checked="element.show_count" @update:checked="element.show_count = $event" />
                      <Label :for="'sc-' + index" class="text-xs font-normal">Показувати лічильник</Label>
                    </div>
                    <div class="flex items-center space-x-2">
                      <Checkbox :id="'sn-' + index" :checked="element.show_new_btn" @update:checked="element.show_new_btn = $event" />
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
      </ScrollArea>

      <DialogFooter class="px-6 py-4 border-t bg-muted/20">
        <Button variant="ghost" @click="$emit('update:open', false)">Скасувати</Button>
        <Button :disabled="isSaving" @click="save">
          <Plus v-if="!isSaving" class="size-4 mr-1.5" />
          Зберегти зміни
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.drag-handle {
  touch-action: none;
}
</style>
