<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Trash2, Pencil, Loader2, CheckCircle, AlertCircle } from '@lucide/vue'
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
    class="relative z-30 flex items-center gap-4 mb-4 px-6 py-4 bg-primary/10 backdrop-blur-md rounded-2xl border border-primary/20 shadow-lg shadow-primary/5 overflow-hidden ring-1 ring-primary/20">
    
    <!-- Background Accents -->
    <div class="absolute -right-8 -top-8 size-32 bg-primary/10 rounded-full blur-3xl pointer-events-none" />
    <div class="absolute -left-8 -bottom-8 size-32 bg-primary/5 rounded-full blur-3xl pointer-events-none" />

    <div class="flex items-center gap-2 shrink-0 relative z-10">
        <div class="size-8 rounded-full bg-primary/20 flex items-center justify-center border border-primary/30">
            <CheckCircle class="size-4 text-primary" />
        </div>
        <span class="text-sm text-foreground font-black tracking-tight">
          {{ t('Selected:') }} 
          <span class="text-primary font-black tabular-nums">{{ allSelected ? `всі ${total ?? count}` : count }}</span>
        </span>
    </div>

    <div class="h-6 w-px bg-primary/20 hidden sm:block relative z-10" />

    <div class="flex flex-wrap items-center gap-2 relative z-10">
        <button
          v-if="isFullPage && total && total > count"
          type="button"
          class="text-xs font-bold text-primary underline-offset-4 hover:underline transition-all mr-2"
          @click="emit('selectAll')"
        >
          Вибрати всі {{ total }} записів
        </button>

        <div class="flex items-center gap-1.5 p-1 bg-background/60 backdrop-blur-sm rounded-xl border border-primary/10 shadow-sm">
            <Button text size="small" class="!px-3 !h-8 !text-xs !font-bold gap-2 hover:!bg-primary/10" @click="openUpdateModal"
              :disabled="!updatableFields.length">
              <Pencil class="size-3.5" />
              <span>Редагувати</span>
            </Button>

            <Button severity="danger" text size="small" class="!px-3 !h-8 !text-xs !font-bold gap-2 hover:!bg-destructive/10" @click="showDeleteModal = true">
              <Trash2 class="size-3.5" />
              <span>{{ t('Delete') }}</span>
            </Button>
        </div>
    </div>

    <Button icon="pi pi-times" text rounded size="small" 
        class="ml-auto !size-8 !text-muted-foreground/40 hover:!text-foreground hover:!bg-muted/20 relative z-10"
        @click="emit('clear')" 
    />

    <!-- Delete confirmation -->
    <Dialog v-model:visible="showDeleteModal" modal
      class="max-w-sm w-full mx-4"
      :pt="{ content: { class: 'p-0 px-6 pb-6 pt-1' } }">
      <template #header>
        <div class="flex items-center gap-3">
            <div class="size-10 rounded-full bg-destructive/10 flex items-center justify-center border border-destructive/20">
                <AlertCircle class="size-5 text-destructive" />
            </div>
            <span class="font-black text-lg">{{ t('Confirm Deletion') }}</span>
        </div>
      </template>
      
      <div class="py-2">
          <p class="text-sm text-muted-foreground leading-relaxed">
              Ви збираєтесь видалити <span class="font-bold text-foreground">{{ displayCount }}</span> записів. 
              Цю дію неможливо буде скасувати. Ви впевнені?
          </p>
      </div>

      <template #footer>
        <div class="flex gap-2 w-full pt-2">
            <Button severity="secondary" outlined class="flex-1" @click="showDeleteModal = false">{{ t('Cancel') }}</Button>
            <Button severity="danger" class="flex-1 shadow-lg shadow-destructive/10" @click="showDeleteModal = false; emit('delete')">{{ t('Delete') }}</Button>
        </div>
      </template>
    </Dialog>

    <!-- Bulk update dialog -->
    <Dialog v-model:visible="showUpdateModal" modal
      header="Масове редагування"
      class="max-w-sm w-full mx-4"
      :pt="{ content: { class: 'p-0 px-6 pb-6 pt-1' } }">
      <template #header>
        <div class="flex items-center gap-3">
            <div class="size-10 rounded-full bg-primary/10 flex items-center justify-center border border-primary/20">
                <Pencil class="size-5 text-primary" />
            </div>
            <span class="font-black text-lg">{{ t('Bulk Update') }}</span>
        </div>
      </template>

      <div class="flex flex-col gap-5 py-2">
        <div class="flex flex-col gap-2">
          <label class="text-[10px] font-bold uppercase tracking-[0.1em] text-muted-foreground">Оберіть поле</label>
          <Select
            v-model="updateField"
            :options="updatableFields"
            option-label="label"
            option-value="fieldname"
            :placeholder="t('Select field...')"
            class="w-full"
            fluid
          />
        </div>
        <div class="flex flex-col gap-2">
          <label class="text-[10px] font-bold uppercase tracking-[0.1em] text-muted-foreground">Нове значення</label>
          <InputText v-model="updateValue" :placeholder="t('Enter value...')"
            class="w-full"
            fluid
            @keydown.enter="submitUpdate" />
        </div>
        
        <div class="p-3 bg-muted/30 rounded-xl border border-border/40">
            <p class="text-[10px] text-muted-foreground leading-tight italic">
                Це оновить поле для всіх <span class="font-bold text-foreground">{{ displayCount }}</span> виділених записів.
            </p>
        </div>
      </div>

      <template #footer>
        <div class="flex gap-2 w-full pt-2">
            <Button outlined severity="secondary" class="flex-1" @click="showUpdateModal = false">{{ t('Cancel') }}</Button>
            <Button class="flex-1 shadow-lg shadow-primary/10" :disabled="!updateField || updateSaving" @click="submitUpdate">
              <Loader2 v-if="updateSaving" class="size-4 animate-spin mr-2" />
              <span>{{ t('Apply') }}</span>
            </Button>
        </div>
      </template>
    </Dialog>
  </div>
</template>
