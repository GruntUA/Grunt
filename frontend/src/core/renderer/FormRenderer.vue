<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, type Component } from 'vue'
import type { DocField, DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { LayoutSection, LayoutTab } from '@/core/composables/useFormLayout'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import { ChevronDown, ChevronLeft, ChevronRight } from '@lucide/vue'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import AppIcon from '@/components/AppIcon.vue'
import FieldRenderer from './FieldRenderer.vue'
import DesignerTab from '../../pages/studio/builder/DesignerTab.vue'
import ViewsTab from '../../pages/studio/builder/tabs/ViewsTab.vue'
import WorkflowGraphTab from '@/components/workflow/WorkflowGraphTab.vue'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, unknown>
  activeTab?: string
  disabled?: boolean
  errors?: Record<string, string>
  overrides?: Record<string, boolean>
  reqdOverrides?: Record<string, boolean>
  dfPropOverrides?: Record<string, Record<string, unknown>>
  fieldLocks?: Record<string, PresenceUser>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  'update:activeTab': [value: string]
  'field-focus': [fieldname: string]
  'field-blur': [fieldname: string]
  'create-new': [doctype: string, preset: string, fieldname: string]
  'table-selection-change': [payload: { fieldname: string; rowNames: string[] }]
}>()

const layout = computed(() => parseLayout(props.doctype.fields))
const hasTabs = computed(() => layout.value.length > 1 || (layout.value[0]?.label !== '' && layout.value[0]?.label !== 'Main'))

const currentTab = computed({
  get: () => props.activeTab || layout.value[0]?.label || 'Main',
  set: (val) => emit('update:activeTab', val)
})

// Reka-ui focuses the active TabsTrigger on mount, which can silently auto-scroll
// the (overflow-x-auto but visually scrollbar-less) tab strip past the first tabs
// when there are enough of them to overflow. Force it back to the start, and
// surface scroll-arrow buttons whenever the tabs don't all fit.
const tabsListRef = ref<{ $el: HTMLElement } | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
let tabsResizeObserver: ResizeObserver | null = null

function updateTabScrollState() {
  const el = tabsListRef.value?.$el
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 0
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
}

function scrollTabsBy(delta: number) {
  tabsListRef.value?.$el.scrollBy({ left: delta, behavior: 'smooth' })
}

onMounted(() => {
  const el = tabsListRef.value?.$el
  if (!el) return
  el.scrollTo({ left: 0 })
  updateTabScrollState()
  tabsResizeObserver = new ResizeObserver(updateTabScrollState)
  tabsResizeObserver.observe(el)
})

onUnmounted(() => tabsResizeObserver?.disconnect())

const customTabComponents: Record<string, Component> = {
  DesignerTab,
  ViewsTab,
  WorkflowGraphTab,
}

function getCustomTabComponent(name: string | undefined): Component | null {
  return name ? (customTabComponents[name] ?? null) : null
}

function hasCustomTabComponent(name: string | undefined): boolean {
  return !!(name && customTabComponents[name])
}

function update(fieldname: string, val: unknown) {
  emit('update:modelValue', { ...props.modelValue, [fieldname]: val })
}

function mergedField(f: DocField): DocField {
  const dfOverrides = props.dfPropOverrides?.[f.fieldname]
  const reqdOverride = props.reqdOverrides?.[f.fieldname]
  if (!dfOverrides && reqdOverride === undefined) return f
  const base: DocField = dfOverrides ? ({ ...f, ...dfOverrides } as DocField) : f
  return reqdOverride !== undefined ? { ...base, required: reqdOverride } : base
}

function toggleSection(section: LayoutSection) {
  if (section.collapsible) section.collapsed = !section.collapsed
}

function isSectionVisible(section: LayoutSection): boolean {
  const sectionField = section._field
  if (!sectionField) return true
  if (sectionField.hidden) return false
  if (!sectionField.depends_on) return true

  const expr = sectionField.depends_on.replace(/^eval:\s*/, '')
  try {
    const doc = props.modelValue ?? {}
    // eslint-disable-next-line no-new-func
    return !!(new Function('doc', `return !!(${expr})`))(doc)
  } catch {
    return true
  }
}

function getVisibleSections(tab: LayoutTab): LayoutSection[] {
  return tab.sections.filter(isSectionVisible)
}
</script>

<template>
  <Tabs v-model="currentTab" class="w-full overflow-hidden">
    <!-- Tab navigation (hidden when there's nothing worth switching between) -->
    <div v-if="hasTabs" class="flex items-center gap-1 mb-4">
      <Button v-if="canScrollLeft" variant="ghost" size="icon" class="size-7 shrink-0" @click="scrollTabsBy(-160)">
        <ChevronLeft class="size-4" />
      </Button>
      <TabsList ref="tabsListRef" class="flex-1 min-w-0 justify-start overflow-x-auto scrollbar-none" @scroll="updateTabScrollState">
        <TabsTrigger v-for="(tab, ti) in layout" :key="ti" :value="tab.label || 'Main'" class="flex-none px-3">
          <AppIcon v-if="tab._field?.icon" :icon="tab._field.icon" class="size-3.5 shrink-0" />
          <span>{{ tab.label || 'Main' }}</span>
        </TabsTrigger>
      </TabsList>
      <Button v-if="canScrollRight" variant="ghost" size="icon" class="size-7 shrink-0" @click="scrollTabsBy(160)">
        <ChevronRight class="size-4" />
      </Button>
    </div>

    <!-- Sections -->
    <TabsContent v-for="(tab, ti) in layout" :key="ti" :value="tab.label || 'Main'"
      class="mt-0 flex flex-col gap-4 focus-visible:ring-0">
      <!-- Support for custom tab components (e.g. Studio Designer) -->
      <template v-if="hasCustomTabComponent(tab._field?.experimental_component)">
        <component :is="getCustomTabComponent(tab._field?.experimental_component)" :doctype="doctype"
          :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" />
      </template>
      <template v-else>
        <div v-for="(section, si) in getVisibleSections(tab)" :key="si"
          :class="[section.label ? 'form-section' : '', 'mb-3 last:mb-0']">

          <!-- Section header (Frappe-style card header) -->
          <div v-if="section.label" class="form-section-header"
            :class="{ 'cursor-pointer select-none': section.collapsible }" @click="toggleSection(section)">
            <ChevronDown v-if="section.collapsible"
              class="size-3.5 text-muted-foreground transition-transform duration-200"
              :class="{ '-rotate-90': section.collapsed }" />
            <span>{{ section.label }}</span>
          </div>

          <!-- Fields layout -->
          <Transition name="section">
            <div v-if="!section.collapsed" :class="section.label ? 'form-section-body' : ''"
              class="grid grid-cols-1 gap-y-5 md:gap-x-5"
              :style="section.columns.length > 1 ? `grid-template-columns: repeat(${Math.min(section.columns.length, 4)}, minmax(0, 1fr))` : ''">
              <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-3 min-w-0">
                <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname"
                  class="relative group" @focusin="emit('field-focus', f.fieldname)"
                  @focusout="emit('field-blur', f.fieldname)">

                  <!-- Field lock badge -->
                  <div v-if="fieldLocks?.[f.fieldname]"
                    class="mb-1 flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-xs font-semibold text-white shadow-sm ring-2 ring-background"
                    :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                    <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                    <span>editing...</span>
                  </div>

                  <FieldRenderer :field="mergedField(f)" :model-value="modelValue[f.fieldname]"
                    :disabled="disabled || f.read_only || !!fieldLocks?.[f.fieldname]" :error="errors?.[f.fieldname]"
                    :doc-values="modelValue" @update:model-value="update(f.fieldname, $event)"
                    @create-new="(doctype, preset, fieldname) => emit('create-new', doctype, preset, fieldname)"
                    @table-selection-change="(fieldname, rowNames) => emit('table-selection-change', { fieldname, rowNames })" />
                </div>
              </div>
            </div>
          </Transition>
        </div>
      </template>
    </TabsContent>
  </Tabs>
</template>

<style scoped>
.section-enter-active,
.section-leave-active {
  transition: opacity 200ms ease, max-height 200ms ease;
  overflow: hidden;
}

.section-enter-from,
.section-leave-to {
  opacity: 0;
  max-height: 0;
}

.section-enter-to,
.section-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* Hide scrollbar but keep functionality */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}

.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
