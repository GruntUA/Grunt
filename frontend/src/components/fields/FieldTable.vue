<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { DocField, DocType } from '@/types'
import { metaApi } from '@/core/api'
import { Plus, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const childDocType = ref<DocType | null>(null)
const rows = ref<Record<string, unknown>[]>([])

const LAYOUT_TYPES = new Set(['Section', 'Column', 'Tab'])

onMounted(async () => {
  if (props.field.options) {
    try { childDocType.value = await metaApi.get(props.field.options) } catch {}
  }
  rows.value = Array.isArray(props.modelValue) ? [...props.modelValue as Record<string, unknown>[]] : []
})

const visibleFields = () =>
  (childDocType.value?.fields ?? []).filter((f) => !LAYOUT_TYPES.has(f.fieldtype) && !f.hidden)

function addRow() {
  rows.value.push({})
  emit('update:modelValue', rows.value)
}

function removeRow(i: number) {
  rows.value.splice(i, 1)
  emit('update:modelValue', [...rows.value])
}

function updateCell(rowIdx: number, fieldname: string, val: unknown) {
  rows.value[rowIdx] = { ...rows.value[rowIdx], [fieldname]: val }
  emit('update:modelValue', [...rows.value])
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="border border-border rounded-lg overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-muted">
          <tr>
            <th v-for="f in visibleFields()" :key="f.fieldname" class="text-left px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border">
              {{ f.label }}
            </th>
            <th v-if="!disabled" class="w-8 border-b border-border" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i" class="border-b border-border last:border-0">
            <td v-for="f in visibleFields()" :key="f.fieldname" class="px-2 py-1">
              <input
                :value="String(row[f.fieldname] ?? '')"
                :disabled="disabled"
                class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none disabled:bg-transparent"
                @input="updateCell(i, f.fieldname, ($event.target as HTMLInputElement).value)"
              />
            </td>
            <td v-if="!disabled" class="px-2 py-1 text-center">
              <button type="button" class="text-muted-foreground hover:text-destructive transition-colors" @click="removeRow(i)">
                <X class="size-4" />
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="visibleFields().length + 1" class="px-3 py-4 text-center text-muted-foreground text-sm">
              Немає рядків
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Button
      v-if="!disabled"
      type="button"
      variant="ghost"
      size="sm"
      class="self-start text-primary"
      @click="addRow"
    >
      <Plus class="size-4 mr-1" />
      Додати рядок
    </Button>
  </div>
</template>
