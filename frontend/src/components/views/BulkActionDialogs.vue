<script setup lang="ts">
/**
 * The bulk dialogs of a list - edit, delete (with replace-on-delete), fast
 * delete. The `bulk` actions in the list header's «Дії ▾» open them through
 * LIST_BULK_UI; the results go back to the list page as events.
 */
import { ref, computed, watch, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2, AlertTriangle, Zap } from '@lucide/vue'
import type { DocField } from '@/types'
import { getNonPhysicalTypeSet, getAsyncFieldComponent } from '@/core/fieldRegistry'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { docsApi, type DeleteImpact } from '@/core/api/docs'
import { LIST_BULK_UI } from '@/core/composables/useListBulkUi'

const props = defineProps<{
  count: number
  total?: number
  allSelected?: boolean
  editableFields?: DocField[]
  doctype?: string
  selectedIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'delete', replaceWith?: string): void
  (e: 'update', field: string, value: unknown): void
  (e: 'fastDelete'): void
}>()

const { t } = useI18n()
const showDeleteModal = ref(false)

// Replace-on-delete: what still references the selected rows
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
  if (g.in_child && g.parent_doctype) parts.push(t('in {doctype}', { doctype: g.parent_doctype }))
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

const displayCount = computed(() =>
  props.allSelected && props.total ? props.total : props.count
)

const NON_PHYSICAL = getNonPhysicalTypeSet()
const updatableFields = computed(() =>
  (props.editableFields ?? []).filter(f => !NON_PHYSICAL.has(f.fieldtype) && !f.read_only)
)

// The field object for the currently picked fieldname - drives which control is
// rendered for the "new value" input (Link picker, Select, Date, Check, …).
const selectedField = computed(() =>
  updatableFields.value.find(f => f.fieldname === updateField.value) ?? null
)
const valueComponent = computed(() =>
  selectedField.value ? getAsyncFieldComponent(selectedField.value.fieldtype) : null
)

// Reset the value whenever the target field changes - a value entered for one
// fieldtype is meaningless for the next.
watch(updateField, () => { updateValue.value = null })

// The dialogs the `bulk` actions ask for - listview.bulk_edit() /
// bulk_delete() / fast_delete() - from the list page.
const bulkUi = inject(LIST_BULK_UI, null)

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
  <!-- Delete confirmation -->
  <Dialog v-model:open="showDeleteModal">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ t('Confirm Deletion') }}</DialogTitle>
        <DialogDescription>
          {{ t('You are about to delete {n} records. This cannot be undone.', { n: String(displayCount) }) }}
        </DialogDescription>
      </DialogHeader>

      <div v-if="impactLoading" class="flex items-center gap-2 text-muted-foreground">
        <Loader2 class="size-4 animate-spin" /> {{ t('Checking links…') }}
      </div>

      <div v-else-if="canReplace && hasRefs" class="grid gap-4">
        <p class="text-muted-foreground">
          {{ t('Other documents link to the selected records') }}
          (<span class="font-medium text-foreground">{{ impact!.total }}</span>).
        </p>
        <ul class="max-h-32 overflow-y-auto rounded-md border divide-y">
          <li v-for="g in impact!.groups" :key="`${g.doctype}-${g.field}`"
            class="flex items-center justify-between gap-3 px-3 py-1.5">
            <span class="truncate">{{ groupLine(g) }}</span>
            <span class="shrink-0 tabular-nums text-muted-foreground">{{ g.count }}</span>
          </li>
        </ul>
        <div class="grid gap-2">
          <Label>{{ t('Replace with') }}</Label>
          <component
            :is="linkComponent"
            :field="replaceField"
            :model-value="replaceWith"
            @update:model-value="replaceWith = ($event as string) ?? ''"
          />
          <p v-if="replaceIsSelf" class="text-destructive">
            {{ t('The replacement cannot be one of the records being deleted.') }}
          </p>
        </div>
        <Label v-if="!canReassign" class="items-start font-normal text-muted-foreground">
          <Checkbox :model-value="ackDangling"
            @update:model-value="ackDangling = $event === true" />
          {{ t('Delete without replacement — {n} links will become invalid.', { n: String(impact!.total) }) }}
        </Label>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="showDeleteModal = false">{{ t('Cancel') }}</Button>
        <Button variant="destructive" :disabled="!canConfirmDelete" @click="confirmDelete">
          {{ canReassign ? t('Delete and reassign') : t('Delete') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Fast delete confirmation (System Manager) -->
  <Dialog v-model:open="showFastDeleteModal">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ t('Fast delete') }}</DialogTitle>
        <DialogDescription>
          {{ t('Delete {n} records directly via SQL — no lifecycle hooks, no per-record ActivityLog.', { n: String(displayCount) }) }}
        </DialogDescription>
      </DialogHeader>

      <Alert variant="destructive">
        <AlertTriangle />
        <AlertDescription>
          {{ t('This cannot be undone. before_delete / after_delete hooks do not run. Use only to bulk-clean test or imported data.') }}
        </AlertDescription>
      </Alert>

      <DialogFooter>
        <Button variant="outline" @click="showFastDeleteModal = false">{{ t('Cancel') }}</Button>
        <Button variant="destructive" @click="showFastDeleteModal = false; emit('fastDelete')">
          <Zap />
          {{ t('Delete') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Bulk update dialog -->
  <Dialog v-model:open="showUpdateModal">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ t('Bulk Update') }}</DialogTitle>
        <DialogDescription>
          {{ t('This updates the field on all {n} selected records.', { n: String(displayCount) }) }}
        </DialogDescription>
      </DialogHeader>

      <div class="grid gap-4">
        <div class="grid gap-2">
          <Label>{{ t('Choose a field') }}</Label>
          <Select v-model="updateField">
            <SelectTrigger class="w-full">
              <SelectValue :placeholder="t('Select field...')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in updatableFields" :key="opt.fieldname" :value="opt.fieldname">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div v-if="selectedField" class="grid gap-2">
          <Label>{{ t('New value') }}</Label>
          <component
            :is="valueComponent"
            :key="selectedField.fieldname"
            :field="selectedField"
            :model-value="updateValue"
            @update:model-value="updateValue = $event"
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="showUpdateModal = false">{{ t('Cancel') }}</Button>
        <Button :disabled="!updateField || updateSaving" @click="submitUpdate">
          <Loader2 v-if="updateSaving" class="animate-spin" />
          {{ t('Apply') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
