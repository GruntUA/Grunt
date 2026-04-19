<script setup lang="ts">
import { ref, computed, shallowRef, onMounted } from 'vue'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import Button from 'primevue/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Search, X } from '@lucide/vue'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

// ── Icon library (lazy-loaded once picker first opens) ──────────────────────
type IconMap = Record<string, Component>
const allIcons = shallowRef<IconMap>({})
const allNames = ref<string[]>([])
let loaded = false

async function ensureLoaded() {
  if (loaded) return
  loaded = true
  const lib = await import('@lucide/vue') as unknown as IconMap
  allIcons.value = lib
  // Extract canonical icon names: PascalCase functions, no *Icon suffix aliases
  allNames.value = Object.keys(lib).filter(k =>
    /^[A-Z]/.test(k) &&
    !k.endsWith('Icon') &&
    (typeof lib[k] === 'function' || typeof lib[k] === 'object')
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function toPascal(kebab: string): string {
  return kebab.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
}

function toKebab(pascal: string): string {
  return pascal.replace(/([A-Z])/g, (_m, l, i) => (i === 0 ? '' : '-') + l.toLowerCase())
}

function getComponent(name: string): Component | null {
  if (!name) return null
  // Accept kebab-case ("fuel", "arrow-left") and PascalCase ("Fuel", "ArrowLeft")
  const pascal = name.includes('-')
    ? toPascal(name)
    : name.charAt(0).toUpperCase() + name.slice(1)
  return (allIcons.value[pascal] ?? null) as Component | null
}

// ── State ─────────────────────────────────────────────────────────────────────
const open = ref(false)
const search = ref('')

const currentName = computed(() => String(props.modelValue ?? ''))
const currentComponent = computed(() => getComponent(currentName.value))

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allNames.value.slice(0, 120)
  return allNames.value.filter(n => n.toLowerCase().includes(q)).slice(0, 200)
})

async function openPicker() {
  if (props.disabled || props.field.read_only) return
  await ensureLoaded()
  open.value = true
}

function select(pascalName: string) {
  emit('update:modelValue', toKebab(pascalName))
  open.value = false
  search.value = ''
}

function clear() {
  emit('update:modelValue', null)
}

// Pre-load icon library if there's already a value so the preview renders immediately
onMounted(() => {
  if (props.modelValue) ensureLoaded()
})
</script>

<template>
  <div class="flex items-center gap-2">
    <!-- Trigger button -->
    <Popover v-model:open="open">
      <PopoverTrigger as-child>
        <Button
          type="button" outlined
          class="h-9 gap-2 min-w-[140px] justify-start font-normal"
          :disabled="disabled || field.read_only"
          @click="openPicker"
        >
          <component :is="currentComponent" v-if="currentComponent" class="size-4 shrink-0" />
          <span v-if="currentName" class="text-sm truncate">{{ currentName }}</span>
          <span v-else class="text-sm text-muted-foreground">Обрати іконку…</span>
        </Button>
      </PopoverTrigger>

      <PopoverContent class="w-80 p-0" align="start" :side-offset="4">
        <!-- Search -->
        <div class="flex items-center gap-2 px-3 py-2.5 border-b border-border/60">
          <Search class="size-3.5 shrink-0 text-muted-foreground" />
          <input
            v-model="search"
            class="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
            placeholder="Пошук іконки…"
            autofocus
          />
          <button v-if="search" type="button" @click="search = ''" class="text-muted-foreground hover:text-foreground">
            <X class="size-3.5" />
          </button>
        </div>

        <!-- Grid -->
        <div class="h-64 overflow-y-auto p-2">
          <div v-if="!allNames.length" class="flex items-center justify-center h-full text-sm text-muted-foreground">
            Завантаження…
          </div>
          <div v-else-if="!filtered.length" class="flex items-center justify-center h-full text-sm text-muted-foreground">
            Не знайдено
          </div>
          <div v-else class="grid grid-cols-8 gap-0.5">
            <button
              v-for="name in filtered"
              :key="name"
              type="button"
              class="flex items-center justify-center rounded p-1.5 transition-colors size-9"
              :class="toKebab(name) === currentName
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-muted text-foreground'"
              :title="toKebab(name)"
              @click="select(name)"
            >
              <component :is="allIcons[name]" class="size-4" />
            </button>
          </div>
          <p v-if="filtered.length === 200 && search" class="text-center text-xs text-muted-foreground mt-2">
            Показано перші 200 результатів
          </p>
          <p v-else-if="!search && allNames.length > 120" class="text-center text-xs text-muted-foreground mt-2 pb-1">
            Введіть назву для пошуку по {{ allNames.length }} іконках
          </p>
        </div>
      </PopoverContent>
    </Popover>

    <!-- Clear button -->
    <button
      v-if="currentName && !disabled && !field.read_only"
      type="button"
      class="text-muted-foreground hover:text-foreground transition-colors"
      @click="clear"
    >
      <X class="size-4" />
    </button>
  </div>
</template>
