<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { DocField, DocType } from '@/types'
import { metaApi } from '@/core/api'

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
    <label class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>

    <div class="border border-[--grunt-border] rounded-[--grunt-radius-md] overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-[--grunt-surface-secondary]">
          <tr>
            <th v-for="f in visibleFields()" :key="f.fieldname" class="text-left px-3 py-2 text-xs font-medium text-[--grunt-text-secondary] border-b border-[--grunt-border]">
              {{ f.label }}
            </th>
            <th v-if="!disabled" class="w-8 border-b border-[--grunt-border]" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i" class="border-b border-[--grunt-border] last:border-0">
            <td v-for="f in visibleFields()" :key="f.fieldname" class="px-2 py-1">
              <input
                :value="String(row[f.fieldname] ?? '')"
                :disabled="disabled"
                class="w-full px-2 py-1 text-sm border border-transparent rounded hover:border-[--grunt-border] focus:border-[--grunt-primary] focus:ring-1 focus:ring-[--grunt-primary]/30 focus:outline-none disabled:bg-transparent"
                @input="updateCell(i, f.fieldname, ($event.target as HTMLInputElement).value)"
              />
            </td>
            <td v-if="!disabled" class="px-2 py-1 text-center">
              <button type="button" class="text-[--grunt-text-muted] hover:text-[--grunt-danger]" @click="removeRow(i)">×</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="visibleFields().length + 1" class="px-3 py-4 text-center text-[--grunt-text-muted] text-sm">
              Немає рядків
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <button
      v-if="!disabled"
      type="button"
      class="text-sm text-[--grunt-primary] hover:underline self-start"
      @click="addRow"
    >+ Додати рядок</button>

    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
