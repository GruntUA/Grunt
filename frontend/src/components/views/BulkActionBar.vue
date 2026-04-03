<script setup lang="ts">
import { ref, computed } from 'vue'
import { Button } from '@/components/ui/button'
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Trash2, X, Pencil, Loader2 } from 'lucide-vue-next'
import type { DocField } from '@/types'

const props = defineProps<{
  count: number
  total?: number
  allSelected?: boolean
  pageCount?: number
  editableFields?: DocField[]
}>()

const emit = defineEmits<{
  (e: 'delete'): void
  (e: 'clear'): void
  (e: 'selectAll'): void
  (e: 'update', field: string, value: string): void
}>()

const showDeleteModal = ref(false)
const showUpdateModal = ref(false)
const updateField = ref('')
const updateValue = ref('')
const updateSaving = ref(false)

const isFullPage = computed(() =>
  !props.allSelected && props.pageCount != null && props.count >= props.pageCount && props.count > 0
)

const displayCount = computed(() =>
  props.allSelected && props.total ? props.total : props.count
)

const NON_PHYSICAL = new Set(['Section', 'Column', 'Tab', 'Table'])
const updatableFields = computed(() =>
  (props.editableFields ?? []).filter(f => !NON_PHYSICAL.has(f.fieldtype) && !f.read_only)
)

function openUpdateModal() {
  updateField.value = updatableFields.value[0]?.fieldname ?? ''
  updateValue.value = ''
  showUpdateModal.value = true
}

async function submitUpdate() {
  if (!updateField.value) return
  updateSaving.value = true
  try {
    emit('update', updateField.value, updateValue.value)
    showUpdateModal.value = false
  } finally {
    updateSaving.value = false
  }
}
</script>

<template>
  <div v-if="count > 0 || allSelected"
    class="flex items-center gap-3 mb-3 px-4 py-2.5 bg-primary/5 rounded-lg border border-primary/20">
    <span class="text-sm text-primary font-medium">
      Вибрано: {{ allSelected ? `всі ${total ?? ''}` : count }}
    </span>

    <button
      v-if="isFullPage && total && total > count"
      type="button"
      class="text-sm text-primary underline hover:text-primary/80 transition-colors"
      @click="emit('selectAll')"
    >
      Обрати всі {{ total }} документів
    </button>

    <Button variant="outline" size="sm" class="text-foreground" @click="openUpdateModal"
      :disabled="!updatableFields.length">
      <Pencil class="size-3.5 mr-1" />
      Змінити поле
    </Button>

    <Button variant="destructive" size="sm" @click="showDeleteModal = true">
      <Trash2 class="size-3.5 mr-1" />
      Видалити{{ allSelected ? ' всі' : '' }}
    </Button>

    <button type="button" class="ml-auto text-muted-foreground hover:text-foreground transition-colors"
      @click="emit('clear')">
      <X class="size-4" />
    </button>

    <!-- Delete confirmation -->
    <AlertDialog :open="showDeleteModal" @update:open="showDeleteModal = $event">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Видалити вибрані записи?</AlertDialogTitle>
          <AlertDialogDescription>
            Буде видалено {{ displayCount }} записів. Цю дію не можна скасувати.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Скасувати</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            @click="showDeleteModal = false; emit('delete')"
          >
            Видалити
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Bulk update dialog -->
    <Dialog :open="showUpdateModal" @update:open="showUpdateModal = $event">
      <DialogContent class="max-w-sm">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <Pencil class="size-4" />
            Змінити поле для {{ displayCount }} записів
          </DialogTitle>
          <DialogDescription class="sr-only">Оберіть поле і введіть нове значення</DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-3 py-1">
          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium text-foreground">Поле</label>
            <Select v-model="updateField">
              <SelectTrigger>
                <SelectValue placeholder="Оберіть поле..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in updatableFields" :key="f.fieldname" :value="f.fieldname">
                  {{ f.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium text-foreground">Нове значення</label>
            <input v-model="updateValue" placeholder="Введіть значення..."
              class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
              @keydown.enter="submitUpdate" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" class="text-foreground" @click="showUpdateModal = false">Скасувати</Button>
          <Button :disabled="!updateField || updateSaving" @click="submitUpdate">
            <Loader2 v-if="updateSaving" class="size-4 animate-spin mr-1.5" />
            Застосувати
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
