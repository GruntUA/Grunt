<script setup lang="ts">
import { ref, watch } from 'vue'
import type { DocField } from '@/types'
import { docsApi } from '@/core/api'
import { Search, X } from 'lucide-vue-next'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const query = ref(String(props.modelValue ?? ''))
const results = ref<{ id: string; name: string }[]>([])
const isOpen = ref(false)
const isLoading = ref(false)
let debounceTimer: ReturnType<typeof setTimeout>
let blurTimer: ReturnType<typeof setTimeout>

watch(() => props.modelValue, (v) => { query.value = String(v ?? '') })

async function onInput(val: string) {
  query.value = val
  emit('update:modelValue', val)
  clearTimeout(debounceTimer)
  if (val.length < 2 || !props.field.options) {
    results.value = []
    isOpen.value = false
    return
  }
  debounceTimer = setTimeout(async () => {
    isLoading.value = true
    try {
      const resp = await docsApi.list(props.field.options!, {
        search: val,
        per_page: 10,
        fields: 'id,name',
      })
      results.value = (resp.data ?? []) as { id: string; name: string }[]
      isOpen.value = true
    } catch {
      results.value = []
    } finally {
      isLoading.value = false
    }
  }, 300)
}

function onBlur() {
  blurTimer = setTimeout(() => { isOpen.value = false }, 200)
}

function onFocus() {
  clearTimeout(blurTimer)
  if (query.value.length >= 2) isOpen.value = true
}

function select(item: { id: string; name: string }) {
  query.value = item.name
  emit('update:modelValue', item.name)
  isOpen.value = false
}

function clear() {
  query.value = ''
  emit('update:modelValue', null)
  isOpen.value = false
}
</script>

<template>
  <div class="relative">
    <div class="relative">
      <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
      <input
        :value="query"
        :placeholder="field.placeholder ?? `Пошук ${field.options ?? ''}...`"
        :disabled="disabled || field.read_only"
        class="w-full rounded-md border border-input bg-transparent pl-8 pr-8 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring disabled:bg-muted disabled:cursor-not-allowed"
        :class="{ 'border-destructive focus-visible:ring-destructive': error }"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @blur="onBlur"
        @focus="onFocus"
      />
      <button
        v-if="modelValue"
        type="button"
        class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
        @mousedown.prevent="clear"
      >
        <X class="size-4" />
      </button>
    </div>

    <!-- Dropdown -->
    <div
      v-if="isOpen"
      class="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto"
    >
      <div v-if="isLoading" class="px-3 py-2 text-sm text-muted-foreground">Завантаження...</div>
      <template v-else-if="results.length">
        <button
          v-for="item in results"
          :key="item.id"
          type="button"
          class="w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors"
          @mousedown.prevent="select(item)"
        >{{ item.name }}</button>
      </template>
      <div v-else class="px-3 py-2 text-sm text-muted-foreground">Нічого не знайдено</div>
    </div>
  </div>
</template>
