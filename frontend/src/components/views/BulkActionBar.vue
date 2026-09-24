<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2, CheckCircle, AlertCircle, X, Zap, Pencil } from '@lucide/vue'
import type { DocField } from '@/types'
import { getNonPhysicalTypeSet, getAsyncFieldComponent } from '@/core/fieldRegistry'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { docsApi, type DeleteImpact } from '@/core/api/docs'
import { LIST_BULK_UI } from '@/core/composables/useListBulkUi'
import ActionIcon from '@/components/views/actions/ActionIcon.vue'

const props = defineProps<{
  count: number
  total?: number
  allSelected?: boolean
  pageCount?: number
  editableFields?: DocField[]
  doctype?: string
  selectedIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'delete', replaceWith?: string): void
  (e: 'clear'): void
  (e: 'selectAll'): void
  (e: 'update', field: string, value: unknown): void
  (e: 'fastDelete'): void
}>()

const { t } = useI18n()
const showDeleteModal = ref(false)

// ── Replace-on-delete: what still references the selected rows ─────────────
const impact = ref<DeleteImpact | null>(null)
const impactLoading = ref(false)
const replaceWith = ref<string>('')
const ackDangling = ref(false)

const canReplace = computed(() =>
  !props.allSelected && !!props.doctype && (props.selectedIds?.length ?? 0) > 0,
)
const hasRefs = computed(() => (impact.value?.total ?? 0) > 0)
const replaceField = computed<DocField>(() => ({
  fieldname: 'replace_with',
  fieldtype: 'Link',
  label: '',
  options: props.doctype ?? '',
} as DocField))
const linkComponent = computed(() => getAsyncFieldComponent('Link'))
const replaceIsSelf = computed(
  () => !!replaceWith.value && (props.selectedIds ?? []).includes(replaceWith.value),
)
const canReassign = computed(() => !!replaceWith.value && !replaceIsSelf.value)
const canConfirmDelete = computed(
  () => canReassign.value || !hasRefs.value || ackDangling.value,
)

function groupLine(g: DeleteImpact['groups'][number]): string {
  const parts = [g.label]
  if (g.field_label) parts.push(g.field_label)
  if (g.in_child && g.parent_doctype) parts.push(`у ${g.parent_doctype}`)
  return parts.join(' · ')
}

watch(showDeleteModal, async (open) => {
  if (!open) {
    impact.value = null
    replaceWith.value = ''
    ackDangling.value = false
    return
  }
  if (!canReplace.value) return
  impactLoading.value = true
  try {
    impact.value = await docsApi.getDeleteImpact(props.doctype!, props.selectedIds!)
  } catch {
    impact.value = null
  } finally {
    impactLoading.value = false
  }
})

function confirmDelete() {
  showDeleteModal.value = false
  emit('delete', canReassign.value ? replaceWith.value : undefined)
}
const showFastDeleteModal = ref(false)
const showUpdateModal = ref(false)
const updateField = ref('')
const updateValue = ref<unknown>(null)
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

// The field object for the currently picked fieldname — drives which control is
// rendered for the "new value" input (Link picker, Select, Date, Check, …).
const selectedField = computed(() =>
  updatableFields.value.find(f => f.fieldname === updateField.value) ?? null
)
const valueComponent = computed(() =>
  selectedField.value ? getAsyncFieldComponent(selectedField.value.fieldtype) : null
)

// Reset the value whenever the target field changes — a value entered for one
// fieldtype is meaningless for the next.
watch(updateField, () => { updateValue.value = null })

// The `bulk` actions (global_list.js + scripts) and the dialogs they ask for —
// listview.bulk_edit() / bulk_delete() / fast_delete() — from the list page.
const bulkUi = inject(LIST_BULK_UI, null)
const bulkActions = computed(() => bulkUi?.actions.value ?? [])

watch(
  () => bulkUi?.request.value,
  (request) => {
    if (!request || !bulkUi) return
    bulkUi.request.value = null
    if (request === 'edit') openUpdateModal()
    else if (request === 'delete') showDeleteModal.value = true
    else if (request === 'fast-delete') showFastDeleteModal.value = true
  },
)

function openUpdateModal() {
  updateField.value = updatableFields.value[0]?.fieldname ?? ''
  updateValue.value = null
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
          <span class="text-muted-foreground">вибрано</span>
        </div>

        <div class="h-4 w-px bg-border" />

        <!-- Select all -->
        <button
          v-if="isFullPage && total && total > count"
          type="button"
          class="font-semibold text-primary hover:underline underline-offset-2 transition-all whitespace-nowrap"
          @click="emit('selectAll')"
        >
          Вибрати всі {{ total }}
        </button>

        <!-- Actions (core/actions.ts, placement: bulk) -->
        <div class="flex items-center gap-1">
          <Button
            v-for="action in bulkActions"
            :key="action.id"
            variant="ghost" size="sm"
            :class="[
              '!px-2.5 !h-7 !text-xs !font-semibold gap-1.5',
              action.variant === 'destructive'
                ? 'text-destructive hover:text-destructive hover:!bg-destructive/10'
                : 'hover:!bg-muted/60',
            ]"
            :disabled="action.disabled"
            @click="action.run()"
          >
            <ActionIcon v-if="action.icon" :name="action.icon" class="size-3" />
            {{ action.label }}
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

    <div class="py-2 flex flex-col gap-3">
      <p class="text-muted-foreground leading-relaxed">
        Ви збираєтесь видалити <span class="font-semibold text-foreground">{{ displayCount }}</span> записів.
        Цю дію неможливо буде скасувати.
      </p>

      <div v-if="impactLoading" class="flex items-center gap-2 text-muted-foreground">
        <Loader2 class="size-4 animate-spin" /> Перевірка посилань…
      </div>

      <template v-else-if="canReplace && hasRefs">
        <p class="text-muted-foreground">
          На виділені записи посилаються інші документи
          (<span class="font-semibold text-foreground">{{ impact!.total }}</span>).
        </p>
        <ul class="max-h-32 overflow-y-auto rounded-md border border-border/60 bg-muted/30 divide-y divide-border/50">
          <li v-for="g in impact!.groups" :key="`${g.doctype}-${g.field}`"
            class="flex items-center justify-between gap-3 px-3 py-1.5">
            <span class="truncate">{{ groupLine(g) }}</span>
            <span class="shrink-0 tabular-nums font-semibold text-muted-foreground">{{ g.count }}</span>
          </li>
        </ul>
        <div class="flex flex-col gap-1.5">
          <label class="font-medium">Підставити замість видалених</label>
          <component
            :is="linkComponent"
            :field="replaceField"
            :model-value="replaceWith"
            @update:model-value="replaceWith = ($event as string) ?? ''"
          />
          <p v-if="replaceIsSelf" class="text-destructive">
            Заміна не може бути одним із записів, що видаляються.
          </p>
        </div>
        <label v-if="!canReassign" class="flex items-start gap-2 cursor-pointer">
          <Checkbox :model-value="ackDangling" class="mt-0.5"
            @update:model-value="ackDangling = $event === true" />
          <span class="text-muted-foreground">
            Видалити без заміни — {{ impact!.total }} посилань стануть недійсними.
          </span>
        </label>
      </template>
    </div>

    <DialogFooter>
      <div class="flex gap-2 w-full pt-2">
        <Button variant="outline" class="flex-1" @click="showDeleteModal = false">{{ t('Cancel') }}</Button>
        <Button variant="destructive" class="flex-1" :disabled="!canConfirmDelete" @click="confirmDelete">
          {{ canReassign ? 'Видалити і перепризначити' : t('Delete') }}
        </Button>
      </div>
    </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Fast delete confirmation (System Manager) -->
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
        <p class="text-destructive font-semibold">
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
        <label class="font-semibold uppercase tracking-[0.1em] text-muted-foreground">Оберіть поле</label>
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
        <label class="font-semibold uppercase tracking-[0.1em] text-muted-foreground">Нове значення</label>
        <component
          :is="valueComponent"
          v-if="selectedField"
          :key="selectedField.fieldname"
          :field="selectedField"
          :model-value="updateValue"
          @update:model-value="updateValue = $event"
        />
      </div>

      <div class="p-3 bg-muted/30 rounded-lg border border-border/40">
        <p class="text-muted-foreground leading-tight italic">
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
