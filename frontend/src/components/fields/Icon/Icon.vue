<script setup lang="ts">
import { ref, computed, shallowRef, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import { Search, X, Check } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Spinner } from '@/components/ui/spinner'
import { Separator } from '@/components/ui/separator'
import { loadLucideLib } from '@/lib/lucide'
import { groupIconsByCategory, CATEGORY_TAB_ICONS } from '@/lib/lucide-categories'

const { t } = useI18n()

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

// ─── Icon Library ────────────────────────────────────────────────────────────

type IconMap = Record<string, Component>
const allIcons = shallowRef<IconMap>({})
const allNames = ref<string[]>([])
let loaded = false

async function ensureLoaded() {
  if (loaded) return
  loaded = true
  const lib = await loadLucideLib() as IconMap
  allIcons.value = lib
  allNames.value = Object.keys(lib).filter(
    k => /^[A-Z]/.test(k) && !k.endsWith('Icon') &&
      (typeof lib[k] === 'function' || typeof lib[k] === 'object'),
  )
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toPascal(kebab: string): string {
  return kebab.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
}

function toKebab(pascal: string): string {
  return pascal.replace(/([A-Z])/g, (_m, l, i) => (i === 0 ? '' : '-') + l.toLowerCase())
}

function getComponent(name: string): Component | null {
  if (!name) return null
  const pascal = name.includes('-')
    ? toPascal(name)
    : name.charAt(0).toUpperCase() + name.slice(1)
  return (allIcons.value[pascal] ?? null) as Component | null
}

// ─── State ───────────────────────────────────────────────────────────────────

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const search = ref('')

const currentName = computed(() => String(props.modelValue ?? ''))
const currentPascal = computed(() =>
  currentName.value ? toPascal(currentName.value) : '')
const currentComponent = computed(() => getComponent(currentName.value))

// ─── Grouped icons ────────────────────────────────────────────────────────────

const MAX_PER_CATEGORY = 64
const MAX_SEARCH = 300

const grouped = computed(() =>
  groupIconsByCategory(allNames.value).map(cat => ({
    ...cat,
    icons: cat.icons.slice(0, MAX_PER_CATEGORY),
  })),
)

const searchGroups = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return grouped.value
  const hits = allNames.value.filter(n => n.toLowerCase().includes(q)).slice(0, MAX_SEARCH)
  if (!hits.length) return []
  return [{ label: t('Results'), icons: hits }]
})

const hasResults = computed(() => searchGroups.value.some(g => g.icons.length > 0))

// ─── Category tabs navigation ─────────────────────────────────────────────────

/** Active category label (tracked via IntersectionObserver) */
const activeCategory = ref('')

/** Refs: the scrollable body and the tab bar */
const scrollBody = ref<HTMLElement | null>(null)
const tabBarRef = ref<HTMLElement | null>(null)

let isScrollingToCategory = false
let scrollEndTimer = 0
let rafId = 0

function handleScroll() {
  if (isScrollingToCategory) return
  cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(updateActiveCategoryOnScroll)
}

function updateActiveCategoryOnScroll() {
  if (isScrollingToCategory || !scrollBody.value) return

  const container = scrollBody.value
  const currentScrollTop = container.scrollTop

  // If at or near the very bottom, highlight the last group
  if (container.scrollHeight - container.clientHeight - currentScrollTop <= 10) {
    const lastGroup = searchGroups.value[searchGroups.value.length - 1]
    if (lastGroup) activeCategory.value = lastGroup.label
    return
  }

  const groupElements = container.querySelectorAll<HTMLElement>('.category-group')
  let currentLabel = ''

  for (const groupEl of groupElements) {
    // 8px tolerance so the header triggers active right when it touches or approaches the top
    if (groupEl.offsetTop <= currentScrollTop + 8) {
      currentLabel = groupEl.dataset.category ?? ''
    } else {
      break
    }
  }

  if (currentLabel && currentLabel !== activeCategory.value) {
    activeCategory.value = currentLabel
  }
}

function onUserScrollInteraction() {
  if (isScrollingToCategory) {
    isScrollingToCategory = false
    clearTimeout(scrollEndTimer)
  }
}

watch(isOpen, async (v) => {
  if (v) {
    await nextTick()
    if (grouped.value.length) activeCategory.value = grouped.value[0].label
  } else {
    search.value = ''
    isScrollingToCategory = false
    clearTimeout(scrollEndTimer)
    cancelAnimationFrame(rafId)
  }
})

// When search clears, reset active category to first group
watch(search, async (q) => {
  if (!q) {
    await nextTick()
    if (grouped.value.length) activeCategory.value = grouped.value[0].label
  }
})

async function scrollToCategory(label: string) {
  if (search.value) {
    search.value = ''
    await nextTick()
  }

  if (!scrollBody.value) return
  const el = scrollBody.value.querySelector<HTMLElement>(`[data-category="${CSS.escape(label)}"]`)
  if (!el) return

  // Because .category-group is a normal-flow child of scrollBody (which has position: relative),
  // el.offsetTop is the exact, constant layout distance from the top of the scroll container.
  // It works equally well whether scrolling forward or backward.
  const targetScrollTop = el.offsetTop

  isScrollingToCategory = true
  activeCategory.value = label

  if (Math.abs(scrollBody.value.scrollTop - targetScrollTop) < 2) {
    isScrollingToCategory = false
    return
  }

  scrollBody.value.scrollTo({ top: targetScrollTop, behavior: 'smooth' })

  clearTimeout(scrollEndTimer)
  const onScrollEnd = () => {
    isScrollingToCategory = false
    clearTimeout(scrollEndTimer)
    scrollBody.value?.removeEventListener('scrollend', onScrollEnd)
  }
  scrollBody.value.addEventListener('scrollend', onScrollEnd, { once: true })
  scrollEndTimer = window.setTimeout(() => {
    isScrollingToCategory = false
    scrollBody.value?.removeEventListener('scrollend', onScrollEnd)
  }, 600)
}

/** Scroll the active tab button into view inside the tab bar */
watch(activeCategory, async (label) => {
  await nextTick()
  if (!tabBarRef.value) return
  const btn = tabBarRef.value.querySelector<HTMLElement>(`[data-cat="${CSS.escape(label)}"]`)
  btn?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
})

// ─── Interactions ─────────────────────────────────────────────────────────────

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

onMounted(() => {
  if (props.modelValue) ensureLoaded()
})

onUnmounted(() => {
  clearTimeout(scrollEndTimer)
  cancelAnimationFrame(rafId)
})
</script>

<template>
  <div class="flex items-center gap-2">
    <!-- Trigger button -->
    <Button
      variant="outline"
      type="button"
      class="h-9 gap-2 min-w-[140px] justify-start font-normal"
      :disabled="disabled || field.read_only"
      :aria-invalid="error ? true : undefined"
      :aria-label="field.label"
      @click="toggle"
    >
      <component :is="currentComponent" v-if="currentComponent" class="size-4 shrink-0" />
      <span v-if="currentName" class="truncate">{{ currentName }}</span>
      <span v-else class="text-muted-foreground">{{ t('Choose an icon…') }}</span>
    </Button>

    <Popover v-model:open="isOpen">
      <PopoverAnchor :reference="anchorEl ?? undefined" />
      <PopoverContent class="w-auto p-0" :side-offset="4">
        <div class="flex w-80 flex-col overflow-hidden rounded-md">

          <!-- ── Search ── -->
          <div class="flex items-center gap-2 border-b px-3 py-2">
            <Search class="size-4 shrink-0 text-muted-foreground" />
            <input
              v-model="search"
              :placeholder="t('Search icons…')"
              class="flex h-8 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              autocomplete="off"
              autofocus
              @keydown.escape.stop="isOpen = false"
            />
            <button
              v-if="search"
              type="button"
              class="shrink-0 rounded-sm opacity-50 hover:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              :aria-label="t('Clear search')"
              @click="search = ''"
            >
              <X class="size-3.5" />
            </button>
          </div>

          <!-- ── Category Tab Bar (hidden while searching) ── -->
          <div
            v-if="!search && allNames.length"
            ref="tabBarRef"
            class="flex items-center gap-0.5 overflow-x-auto border-b px-1.5 py-1 scrollbar-none"
            role="tablist"
            :aria-label="t('Icon categories')"
          >
            <button
              v-for="cat in grouped"
              :key="cat.label"
              type="button"
              role="tab"
              :data-cat="cat.label"
              :aria-selected="activeCategory === cat.label"
              :title="cat.label"
              :aria-label="cat.label"
              :class="[
                'relative flex shrink-0 size-8 items-center justify-center rounded-md transition-colors',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                activeCategory === cat.label
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent',
              ]"
              @click="scrollToCategory(cat.label)"
            >
              <component
                :is="allIcons[CATEGORY_TAB_ICONS[cat.label] ?? cat.icons[0]]"
                class="size-4"
              />
              <!-- Active underline -->
              <span
                v-if="activeCategory === cat.label"
                class="absolute bottom-0 left-1/2 h-0.5 w-4 -translate-x-1/2 rounded-full bg-primary"
              />
            </button>
          </div>

          <!-- ── Loading ── -->
          <div v-if="!allNames.length" class="flex items-center justify-center h-48">
            <Spinner />
          </div>

          <!-- ── Empty search results ── -->
          <div
            v-else-if="!hasResults"
            class="py-10 text-center text-sm text-muted-foreground"
          >
            {{ t('No icons found') }}
          </div>

          <!-- ── Icon grid (grouped) ── -->
          <div
            v-else
            ref="scrollBody"
            class="relative max-h-[300px] overflow-y-auto overflow-x-hidden"
            @scroll.passive="handleScroll"
            @wheel.passive="onUserScrollInteraction"
            @touchstart.passive="onUserScrollInteraction"
          >
            <div
              v-for="(group, gi) in searchGroups"
              :key="group.label"
              :data-category="group.label"
              class="category-group"
            >
              <!-- Group heading (sticky within its category-group container) -->
              <div
                class="sticky top-0 z-10 bg-popover/95 backdrop-blur-sm px-3 py-1.5"
              >
                <p class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground select-none">
                  {{ group.label }}
                </p>
              </div>

              <!-- Icon grid -->
              <div class="grid grid-cols-8 gap-0.5 px-2 pb-2">
                <button
                  v-for="name in group.icons"
                  :key="name"
                  type="button"
                  :title="toKebab(name)"
                  :aria-label="toKebab(name)"
                  :aria-pressed="name === currentPascal"
                  :class="[
                    'relative flex size-8 items-center justify-center rounded-md transition-colors',
                    'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                    'hover:bg-accent hover:text-accent-foreground',
                    name === currentPascal
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                      : 'text-foreground/80',
                  ]"
                  @click="select(name)"
                >
                  <component :is="allIcons[name]" class="size-4" />
                  <!-- Selected checkmark badge -->
                  <span
                    v-if="name === currentPascal"
                    class="absolute -top-0.5 -right-0.5 flex size-2.5 items-center justify-center rounded-full bg-primary-foreground"
                  >
                    <Check class="size-2 text-primary stroke-[3]" />
                  </span>
                </button>
              </div>

              <Separator v-if="gi < searchGroups.length - 1" class="my-0.5 mx-2 w-auto" />
            </div>

            <!-- Hint -->
            <p v-if="!search && allNames.length > 120" class="px-3 py-2 text-center text-xs text-muted-foreground">
              {{ t('Type to search all {n} icons', { n: allNames.length }) }}
            </p>
          </div>

        </div>
      </PopoverContent>
    </Popover>

    <!-- Clear button -->
    <Button
      v-if="currentName && !disabled && !field.read_only"
      type="button"
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
