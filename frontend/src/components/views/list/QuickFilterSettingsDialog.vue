<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'
import type { DocType } from '@/types'
import { SUPPORTED_FIELD_TYPES } from '@/core/quickFilters'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

const props = defineProps<{
  open: boolean
  dt: DocType
  /** Currently effective quick-filter fields (personal override or doctype defaults). */
  currentFields: string[]
}>()

const emit = defineEmits<{
  'update:open': [val: boolean]
  save: [fields: string[]]
  reset: []
}>()

const { t } = useI18n()

const search = ref('')
const selected = ref<Set<string>>(new Set())

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    search.value = ''
    selected.value = new Set(props.currentFields)
  }
})

const eligibleFields = computed(() =>
  props.dt.fields.filter((f) => SUPPORTED_FIELD_TYPES.has(f.fieldtype))
)

const filteredFields = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return eligibleFields.value
  return eligibleFields.value.filter((f) =>
    f.label.toLowerCase().includes(q) || f.fieldname.toLowerCase().includes(q)
  )
})

function toggle(fieldname: string) {
  const next = new Set(selected.value)
  if (next.has(fieldname)) next.delete(fieldname)
  else next.add(fieldname)
  selected.value = next
}

function handleSave() {
  // Preserve the doctype's own field order, not checkbox-click order.
  const ordered = props.dt.fields
    .map((f) => f.fieldname)
    .filter((fieldname) => selected.value.has(fieldname))
  emit('save', ordered)
  emit('update:open', false)
}

function handleReset() {
  emit('reset')
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ t('Обрати фільтри') }}</DialogTitle>
      </DialogHeader>

      <p class="text-muted-foreground -mt-2">
        {{ t('Особисте налаштування — лише для вас, на цьому пристрої.') }}
      </p>

      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input v-model="search" class="pl-9" :placeholder="t('Пошук...')" />
      </div>

      <p class="font-medium text-muted-foreground uppercase tracking-wide">
        {{ dt.label }}
      </p>

      <div class="grid grid-cols-2 gap-x-4 gap-y-2 max-h-[320px] overflow-y-auto">
        <label
          v-for="f in filteredFields" :key="f.fieldname"
          class="flex items-center gap-2 cursor-pointer"
        >
          <Checkbox
            :model-value="selected.has(f.fieldname)"
            @update:model-value="toggle(f.fieldname)"
          />
          {{ f.label }}
        </label>
        <p v-if="!filteredFields.length" class="col-span-2 text-muted-foreground text-center py-4">
          {{ t('Нічого не знайдено') }}
        </p>
      </div>

      <DialogFooter class="sm:justify-between">
        <Button variant="ghost" class="text-muted-foreground" @click="handleReset">
          {{ t('Скинути до типових') }}
        </Button>
        <div class="flex gap-2">
          <Button variant="outline" @click="emit('update:open', false)">{{ t('Скасувати') }}</Button>
          <Button @click="handleSave">{{ t('Зберегти') }}</Button>
        </div>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
