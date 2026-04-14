<script setup lang="ts">
import { ref, watch } from 'vue'
import { Input } from '@/components/ui/input'
import { X, Loader2 } from 'lucide-vue-next'
import type { DocField } from '@/types'
import type { LinkSearchItem } from '@/core/api/docs'
import { docsApi } from '@/core/api/docs'

const props = defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()

const linkQuery = ref(props.displayValue || props.modelValue)
const linkResults = ref<LinkSearchItem[]>([])
const linkLoading = ref(false)
const _suppressClear = ref(false)

// Sync query when parent sets displayValue (e.g. when editing an existing filter)
watch(() => props.displayValue, (v) => {
  if (v && v !== linkQuery.value) {
    _suppressClear.value = true
    linkQuery.value = v
    setTimeout(() => { _suppressClear.value = false }, 0)
  }
})

let debounce: ReturnType<typeof setTimeout>
watch(linkQuery, (q) => {
  if (_suppressClear.value) return
  clearTimeout(debounce)
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  if (!q.trim()) { linkResults.value = []; return }
  debounce = setTimeout(() => search(q), 280)
})

async function search(q: string) {
  const linkedDoctype = props.field.options
  if (!linkedDoctype || typeof linkedDoctype !== 'string') return
  linkLoading.value = true
  try {
    linkResults.value = await docsApi.linkSearch(linkedDoctype, q)
  } catch {
    linkResults.value = []
  } finally {
    linkLoading.value = false
  }
}

function selectItem(item: LinkSearchItem) {
  emit('update:modelValue', item.name)
  emit('update:displayValue', item.title || item.name)
  linkQuery.value = item.title || item.name
  linkResults.value = []
}

function clear() {
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  linkQuery.value = ''
}
</script>

<template>
  <div class="mb-3 space-y-1.5">
    <div class="relative">
      <Input
        v-model="linkQuery"
        class="h-8 text-xs pr-7"
        :placeholder="`Пошук ${field.options}...`"
        @keydown.enter.prevent="linkResults[0] && selectItem(linkResults[0])"
      />
      <Loader2 v-if="linkLoading" class="absolute right-2 top-1/2 -translate-y-1/2 size-3.5 animate-spin text-muted-foreground" />
    </div>

    <div v-if="linkResults.length" class="border border-border rounded-md overflow-hidden max-h-40 overflow-y-auto divide-y divide-border/60">
      <button
        v-for="item in linkResults"
        :key="item.id"
        type="button"
        class="w-full px-3 py-2 text-left text-xs hover:bg-primary/5 transition-colors flex items-center gap-2"
        :class="modelValue === item.name ? 'bg-primary/10' : ''"
        @click="selectItem(item)"
      >
        <span class="font-medium text-foreground truncate flex-1">{{ item.title || item.name }}</span>
        <span v-if="item.subtitle" class="text-muted-foreground/60 shrink-0 truncate max-w-[80px]">{{ item.subtitle }}</span>
      </button>
    </div>
    <p v-else-if="linkQuery && !linkLoading && !modelValue" class="text-xs text-muted-foreground/60 italic px-1">
      Нічого не знайдено
    </p>

    <div v-if="modelValue" class="flex items-center gap-1.5 px-2 py-1 bg-primary/5 border border-primary/20 rounded-md text-xs text-primary">
      <span class="truncate flex-1">{{ displayValue || modelValue }}</span>
      <button type="button" class="shrink-0 hover:text-destructive" @click="clear">
        <X class="size-3" />
      </button>
    </div>
  </div>
</template>
