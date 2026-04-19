<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Trash2, X, Pencil, Loader2 } from '@lucide/vue'
import type { DocField } from '@/types'
import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'

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

const { t } = useI18n()
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
  <div v-if="count > 0 || allSelected"
    class="flex items-center gap-3 mb-3 px-4 py-2.5 bg-primary/5 rounded-lg border border-primary/20">
    <span class="text-sm text-primary font-medium">
      {{ t('Selected:') }} {{ allSelected ? `всі ${total ?? count}` : count }}
    </span>

    <button
      v-if="isFullPage && total && total > count"
      type="button"
      class="text-sm text-primary underline hover:text-primary/80 transition-colors"
      @click="emit('selectAll')"
    >
      Вибрати всі {{ total }} записів
    </button>

    <Button outlined size="small" class="text-foreground" @click="openUpdateModal"
      :disabled="!updatableFields.length">
      <Pencil class="size-3.5 mr-1" />
      {{ t('Edit field') }}
    </Button>

    <Button severity="danger" size="small" @click="showDeleteModal = true">
      <Trash2 class="size-3.5 mr-1" />
      {{ t('Delete') }}{{ allSelected ? ' всі' : '' }}
    </Button>

    <button type="button" class="ml-auto text-muted-foreground hover:text-foreground transition-colors"
      @click="emit('clear')">
      <X class="size-4" />
    </button>

    <!-- Delete confirmation -->
    <Dialog v-model:visible="showDeleteModal" modal :closable="false"
      :pt="{ root: { class: 'max-w-sm' }, content: { class: 'p-0 px-6 pb-4 pt-2' } }">
      <template #header>
        <span class="font-semibold text-base">{{ t('Delete selected records?') }}</span>
      </template>
      <p class="text-sm text-muted-foreground">Буде видалено {{ displayCount }} записів. Цю дію не можна скасувати.</p>
      <template #footer>
        <Button severity="secondary" text @click="showDeleteModal = false">{{ t('Cancel') }}</Button>
        <Button severity="danger" @click="showDeleteModal = false; emit('delete')">{{ t('Delete') }}</Button>
      </template>
    </Dialog>

    <!-- Bulk update dialog -->
    <Dialog v-model:visible="showUpdateModal" modal
      :pt="{ root: { class: 'max-w-sm' }, content: { class: 'p-0 px-6 pb-4 pt-1' } }">
      <template #header>
        <span class="flex items-center gap-2 font-semibold">
          <Pencil class="size-4" />
          {{ t('Edit field for {count} records', { count: displayCount }) }}
        </span>
      </template>
      <div class="flex flex-col gap-3 py-1">
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Поле</label>
          <Select
            v-model="updateField"
            :options="updatableFields"
            option-label="label"
            option-value="fieldname"
            :placeholder="t('Select field...')"
            class="w-full"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">{{ t('New value') }}</label>
          <input v-model="updateValue" :placeholder="t('Enter value...')"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitUpdate" />
        </div>
      </div>
      <template #footer>
        <Button outlined class="text-foreground" @click="showUpdateModal = false">{{ t('Cancel') }}</Button>
        <Button :disabled="!updateField || updateSaving" @click="submitUpdate">
          <Loader2 v-if="updateSaving" class="size-4 animate-spin mr-1.5" />
          {{ t('Apply') }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>
