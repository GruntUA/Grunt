<script setup lang="ts">
import { ref, computed, shallowRef, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import { Search, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Spinner } from '@/components/ui/spinner'
import { loadLucideLib } from '@/lib/lucide'

const { t } = useI18n()

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

// Icon library (lazy-loaded once picker first opens)
type IconMap = Record<string, Component>
const allIcons = shallowRef<IconMap>({})
const allNames = ref<string[]>([])
let loaded = false

async function ensureLoaded() {
  if (loaded) return
  loaded = true
  const lib = await loadLucideLib() as IconMap
  allIcons.value = lib
  // Extract canonical icon names: PascalCase functions, no *Icon suffix aliases
  allNames.value = Object.keys(lib).filter(k =>
    /^[A-Z]/.test(k) &&
    !k.endsWith('Icon') &&
    (typeof lib[k] === 'function' || typeof lib[k] === 'object')
  )
}

// Helpers
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

// State
const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const search = ref('')

const currentName = computed(() => String(props.modelValue ?? ''))
const currentComponent = computed(() => getComponent(currentName.value))

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allNames.value.slice(0, 120)
  return allNames.value.filter(n => n.toLowerCase().includes(q)).slice(0, 200)
})

async function toggle(event: Event) {
  if (props.disabled || props.field.read_only) return
  const target = event.currentTarget as HTMLElement
  await ensureLoaded()
  anchorEl.value = target
  isOpen.value = !isOpen.value
}

function select(pascalName: string) {
  emit('update:modelValue', toKebab(pascalName))
  isOpen.value = false
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
    <Button variant="outline" type="button" class="h-9 gap-2 min-w-[140px] justify-start font-normal" :disabled="disabled || field.read_only" :aria-invalid="error ? true : undefined" :aria-label="field.label" @click="toggle">
        <component :is="currentComponent" v-if="currentComponent" class="size-4 shrink-0" />
        <span v-if="currentName" class="truncate">{{ currentName }}</span>
        <span v-else class="text-muted-foreground">{{ t('Choose an icon…') }}</span>
    </Button>

    <Popover v-model:open="isOpen">
      <PopoverAnchor :reference="anchorEl ?? undefined" />
      <PopoverContent class="w-auto p-0">
        <div class="w-80 flex flex-col overflow-hidden">
            <!-- Search -->
            <div class="border-b p-2">
                <InputGroup>
                    <InputGroupAddon><Search /></InputGroupAddon>
                    <InputGroupInput v-model="search" :placeholder="t('Search icon…')" :aria-label="t('Search icon…')" autofocus />
                    <InputGroupAddon v-if="search" align="inline-end">
                        <InputGroupButton type="button" size="icon-xs" :aria-label="t('Clear')" @click="search = ''"><X /></InputGroupButton>
                    </InputGroupAddon>
                </InputGroup>
            </div>

            <!-- Grid -->
            <div class="h-64 overflow-y-auto p-2">
                <div v-if="!allNames.length" class="flex items-center justify-center h-full text-muted-foreground">
                    <Spinner />
                </div>
                <div v-else-if="!filtered.length" class="flex items-center justify-center h-full text-muted-foreground">
                    {{ t('Nothing found') }}
                </div>
                <div v-else class="grid grid-cols-8 gap-0.5">
                    <Button type="button"
                        v-for="name in filtered"
                        :key="name"
                        :variant="toKebab(name) === currentName ? 'default' : 'ghost'"
                        size="icon"
                        :title="toKebab(name)"
                        :aria-label="toKebab(name)"
                        :aria-pressed="toKebab(name) === currentName"
                        @click="select(name)"
                    >
                        <component :is="allIcons[name]" />
                    </Button>
                </div>
                <p v-if="filtered.length === 200 && search" class="text-center text-muted-foreground mt-2">
                    {{ t('Showing first {n} results', { n: 200 }) }}
                </p>
                <p v-else-if="!search && allNames.length > 120" class="text-center text-muted-foreground mt-2 pb-1">
                    {{ t('Type to search {n} icons', { n: allNames.length }) }}
                </p>
            </div>
        </div>
      </PopoverContent>
    </Popover>

    <!-- Clear button -->
    <Button type="button"
      v-if="currentName && !disabled && !field.read_only"
      variant="ghost"
      size="icon-sm"
      class="text-muted-foreground"
      :aria-label="t('Clear')"
      @click="clear"
    >
      <X />
    </Button>
  </div>
</template>
