<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Trash2, Pencil, Loader2, CheckCircle, AlertCircle, X, Zap } from '@lucide/vue'
import type { DocField } from '@/types'
import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const props = defineProps<{
  count: number
  total?: number
  allSelected?: boolean
  pageCount?: number
  editableFields?: DocField[]
  isSuperadmin?: boolean
}>()

const emit = defineEmits<{
  (e: 'delete'): void
  (e: 'clear'): void
  (e: 'selectAll'): void
  (e: 'update', field: string, value: string): void
  (e: 'fastDelete'): void
}>()

const { t } = useI18n()
const showDeleteModal = ref(false)
const showFastDeleteModal = ref(false)
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

const NON_PHYSICAL = getNonPhysicalTypeSet()
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
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-4 opacity-0"
    >
      <div v-if="count > 0 || allSelected"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-2.5 rounded-lg border border-primary/25 bg-background/90 shadow-md">

        <!-- Count -->
        <div class="flex items-center gap-2 shrink-0">
          <div class="size-5 rounded-full bg-primary/20 flex items-center justify-center">
            <CheckCircle class="size-3 text-primary" />
          </div>
          <span class="font-semibold text-foreground tabular-nums">
            {{ allSelected ? `всі ${total ?? count}` : count }}
          </span>
          <span class="text-xs text-muted-foreground">вибрано</span>
        </div>

        <div class="h-4 w-px bg-border" />

        <!-- Select all -->
        <button
          v-if="isFullPage && total && total > count"
          type="button"
          class="text-xs font-semibold text-primary hover:underline underline-offset-2 transition-all whitespace-nowrap"
          @click="emit('selectAll')"
        >
          Вибрати всі {{ total }}
        </button>

        <!-- Actions -->
        <div class="flex items-center gap-1">
          <Button variant="ghost" size="sm" class="!px-2.5 !h-7 !text-xs !font-semibold gap-1.5 hover:!bg-muted/60" :disabled="!updatableFields.length" @click="openUpdateModal">
            <Pencil class="size-3" />
            Редагувати
          </Button>

          <Button
            variant="ghost" size="sm"
            class="!px-2.5 !h-7 !text-xs !font-semibold gap-1.5 text-destructive hover:text-destructive hover:!bg-destructive/10"
            @click="showDeleteModal = true"
          >
            <Trash2 class="size-3" />
            Видалити
          </Button>

          <!-- Fast delete — superadmin only, only when all records selected -->
          <Button
            v-if="isSuperadmin && allSelected"
            variant="ghost" size="sm"
            class="!px-2.5 !h-7 !text-xs !font-semibold gap-1.5 text-destructive hover:text-destructive hover:!bg-destructive/10 opacity-80"
            @click="showFastDeleteModal = true"
          >
            <Zap class="size-3" />
            Швидке видалення
          </Button>
        </div>

        <div class="h-4 w-px bg-border" />

        <!-- Close -->
        <button
          type="button"
          class="size-6 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          @click="emit('clear')"
        >
          <X class="size-3.5" />
        </button>
      </div>
    </Transition>
  </Teleport>

  <!-- Delete confirmation -->
  <Dialog v-model:open="showDeleteModal">
    <DialogContent class="max-w-sm w-full mx-4 p-0 px-6 pb-6 pt-1">
    <DialogHeader>
      <div class="flex items-center gap-3">
        <div class="size-10 rounded-full bg-destructive/10 flex items-center justify-center border border-destructive/20">
          <AlertCircle class="size-5 text-destructive" />
        </div>
        <DialogTitle class="font-semibold text-lg">{{ t('Confirm Deletion') }}</DialogTitle>
      </div>
    </DialogHeader>

    <div class="py-2">
      <p class="text-muted-foreground leading-relaxed">
        Ви збираєтесь видалити <span class="font-semibold text-foreground">{{ displayCount }}</span> записів.
        Цю дію неможливо буде скасувати. Ви впевнені?
      </p>
    </div>

    <DialogFooter>
      <div class="flex gap-2 w-full pt-2">
        <Button variant="outline" class="flex-1" @click="showDeleteModal = false">{{ t('Cancel') }}</Button>
        <Button variant="destructive" class="flex-1" @click="showDeleteModal = false; emit('delete')">{{ t('Delete') }}</Button>
      </div>
    </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Fast delete confirmation (superadmin) -->
  <Dialog v-model:open="showFastDeleteModal">
    <DialogContent class="max-w-sm w-full mx-4 p-0 px-6 pb-6 pt-1">
    <DialogHeader>
      <div class="flex items-center gap-3">
        <div class="size-10 rounded-full bg-destructive/10 flex items-center justify-center border border-destructive/20">
          <Zap class="size-5 text-destructive" />
        </div>
        <DialogTitle class="font-semibold text-lg">Швидке видалення</DialogTitle>
      </div>
    </DialogHeader>

    <div class="py-2 flex flex-col gap-3">
      <p class="text-muted-foreground leading-relaxed">
        Видалити <span class="font-semibold text-foreground">{{ displayCount }}</span> записів напряму через SQL
        — без lifecycle хуків, ActivityLog per-record.
      </p>
      <div class="p-3 bg-destructive/5 border border-destructive/20 rounded-lg">
        <p class="text-xs text-destructive font-semibold">
          ⚡ Це незворотна операція. Хуки <code>before_delete</code> / <code>after_delete</code> не виконуються.
          Використовуй лише для масового очищення тестових або імпортованих даних.
        </p>
      </div>
    </div>

    <DialogFooter>
      <div class="flex gap-2 w-full pt-2">
        <Button variant="outline" class="flex-1" @click="showFastDeleteModal = false">Скасувати</Button>
        <Button variant="destructive" class="flex-1" @click="showFastDeleteModal = false; emit('fastDelete')">
          <Zap class="size-4 mr-1" />
          Видалити
        </Button>
      </div>
    </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Bulk update dialog -->
  <Dialog v-model:open="showUpdateModal">
    <DialogContent class="max-w-sm w-full mx-4 p-0 px-6 pb-6 pt-1">
    <DialogHeader>
      <div class="flex items-center gap-3">
        <div class="size-10 rounded-full bg-primary/10 flex items-center justify-center border border-primary/20">
          <Pencil class="size-5 text-primary" />
        </div>
        <DialogTitle class="font-semibold text-lg">{{ t('Bulk Update') }}</DialogTitle>
      </div>
    </DialogHeader>

    <div class="flex flex-col gap-5 py-2">
      <div class="flex flex-col gap-2">
        <label class="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Оберіть поле</label>
        <Select v-model="updateField">
          <SelectTrigger class="w-full">
            <SelectValue :placeholder="t('Select field...')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in updatableFields" :key="opt.fieldname" :value="opt.fieldname">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div class="flex flex-col gap-2">
        <label class="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Нове значення</label>
        <Input v-model="updateValue" :placeholder="t('Enter value...')"
          class="w-full"
          fluid
          @keydown.enter="submitUpdate" />
      </div>

      <div class="p-3 bg-muted/30 rounded-lg border border-border/40">
        <p class="text-xs text-muted-foreground leading-tight italic">
          Це оновить поле для всіх <span class="font-semibold text-foreground">{{ displayCount }}</span> виділених записів.
        </p>
      </div>
    </div>

    <DialogFooter>
      <div class="flex gap-2 w-full pt-2">
        <Button variant="outline" class="flex-1" @click="showUpdateModal = false">{{ t('Cancel') }}</Button>
        <Button class="flex-1" :disabled="!updateField || updateSaving" @click="submitUpdate">
          <Loader2 v-if="updateSaving" class="size-4 animate-spin mr-2" />
          <span>{{ t('Apply') }}</span>
        </Button>
      </div>
    </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
