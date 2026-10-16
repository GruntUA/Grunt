<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, provide, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizeObserver } from '@vueuse/core'
import type { DocField, DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import { evalDependsOn } from '@/core/dependsOn'
import { FORM_ERRORS } from './formErrors'
import type { LayoutSection, LayoutTab } from '@/core/composables/useFormLayout'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import { ChevronDown, ChevronLeft, ChevronRight } from '@lucide/vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import AppIcon from '@/components/AppIcon.vue'
import FieldRenderer from './FieldRenderer.vue'
import DocConnections from '@/components/views/form/DocConnections.vue'
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
  workspace?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  'update:activeTab': [value: string]
  'field-focus': [fieldname: string]
  'field-blur': [fieldname: string]
  'create-new': [doctype: string, preset: string | Record<string, unknown>, fieldname: string]
  'table-selection-change': [payload: { fieldname: string; rowNames: string[] }]
}>()

const { t } = useI18n()

// Expose the validation-error map to the whole field tree (nested sub-forms
// re-provide it with an extended path prefix).
provide(FORM_ERRORS, {
  errors: computed(() => props.errors ?? {}),
  prefix: '',
})

// Heavy studio tabs (builder, Vue Flow) are loaded only by the DocTypes that use them.
const customTabComponents: Record<string, Component> = {
  DesignerTab: defineAsyncComponent(() => import('../../pages/studio/builder/DesignerTab.vue')),
  WebFormDesignerTab: defineAsyncComponent(() => import('../../pages/studio/builder/webform/WebFormDesignerTab.vue')),
  WorkflowGraphTab: defineAsyncComponent(() => import('@/components/workflow/WorkflowGraphTab.vue')),
}

const docValues = computed(() => props.modelValue ?? {})

const parsedLayout = computed(() => parseLayout(props.doctype.fields))

// Fields with script overrides applied. Independent of the document values, so
// the objects stay stable while the user types.
const mergedFields = computed(() => {
  const map = new Map<string, DocField>()
  for (const f of props.doctype.fields) {
    // The workflow state moves only by the header's workflow actions and is shown
    // in the document sidebar - no read-only duplicate in the form.
    if (f.fieldname === props.doctype.workflow_state_field) {
      map.set(f.fieldname, { ...f, hidden: true })
      continue
    }
    const dfOverrides = props.dfPropOverrides?.[f.fieldname]
    const reqdOverride = props.reqdOverrides?.[f.fieldname]
    if (!dfOverrides && reqdOverride === undefined) continue
    const base: DocField = dfOverrides ? ({ ...f, ...dfOverrides } as DocField) : f
    map.set(f.fieldname, reqdOverride !== undefined ? { ...base, required: reqdOverride } : base)
  }
  return map
})

function mergedField(f: DocField): DocField {
  return mergedFields.value.get(f.fieldname) ?? f
}

function isFieldVisible(f: DocField): boolean {
  if (props.overrides?.[f.fieldname] === false) return false
  const field = mergedField(f)
  return !field.hidden && evalDependsOn(field.depends_on, docValues.value)
}

function isSectionVisible(section: LayoutSection): boolean {
  const sectionField = section._field
  if (sectionField?.hidden) return false
  if (sectionField && !evalDependsOn(sectionField.depends_on, docValues.value)) return false
  // A section whose fields are all hidden would render as an empty gap.
  return section.columns.some((col) => col.some(isFieldVisible))
}

interface VisibleTab {
  tab: LayoutTab
  component: Component | null
  sections: LayoutSection[]
}

// A Tab's own `depends_on` hides the whole tab (e.g. tree settings for a non-tree DocType).
const layout = computed<VisibleTab[]>(() =>
  parsedLayout.value
    .filter((tab) => !tab._field || (!tab._field.hidden && evalDependsOn(tab._field.depends_on, docValues.value)))
    .map((tab) => {
      const name = tab._field?.tab_component
      const component = (name && customTabComponents[name]) || null
      return { tab, component, sections: component ? [] : tab.sections.filter(isSectionVisible) }
    }),
)
const hasTabs = computed(() => {
  const first = layout.value[0]?.tab
  return layout.value.length > 1 || (first?.label !== '' && first?.label !== 'Main')
})

// The "Зв'язки" panel is placed inside whichever Tab has `show_connections`
// set, falling back to the first tab. Only shown for a saved, non-child doc.
const connectionsTabId = computed<string | null>(() => {
  if (props.doctype.is_child || !docValues.value.name) return null
  const opted = layout.value.find(({ tab }) => tab._field?.show_connections)
  return (opted ?? layout.value[0])?.tab._fieldname || null
})

const currentTab = computed({
  get: () =>
    (props.activeTab && layout.value.some(({ tab }) => tab._fieldname === props.activeTab)
      ? props.activeTab
      : layout.value[0]?.tab._fieldname) || '',
  set: (val) => emit('update:activeTab', val)
})

// Reka-ui focuses the active TabsTrigger on mount, which can silently auto-scroll
// the (overflow-x-auto but visually scrollbar-less) tab strip past the first tabs
// when there are enough of them to overflow. Force it back to the start, and
// surface scroll-arrow buttons whenever the tabs don't all fit.
const tabsListRef = ref<{ $el: HTMLElement } | null>(null)
const tabsListEl = computed(() => tabsListRef.value?.$el ?? null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)

function updateTabScrollState() {
  const el = tabsListEl.value
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 0
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
}

function scrollTabsBy(delta: number) {
  tabsListEl.value?.scrollBy({ left: delta, behavior: 'smooth' })
}

watch(tabsListEl, (el) => {
  el?.scrollTo({ left: 0 })
  updateTabScrollState()
})
useResizeObserver(tabsListEl, updateTabScrollState)
// Tabs shown/hidden by `depends_on` change scrollWidth without resizing the strip.
watch(() => layout.value.length, () => nextTick(updateTabScrollState))

function update(fieldname: string, val: unknown) {
  emit('update:modelValue', { ...props.modelValue, [fieldname]: val })
}

function onCreateNew(doctype: string, preset: string | Record<string, unknown>, fieldname: string) {
  emit('create-new', doctype, preset, fieldname)
}

function onTableSelectionChange(fieldname: string, rowNames: string[]) {
  emit('table-selection-change', { fieldname, rowNames })
}

// Columns collapse by the section's own width (container query), not the
// viewport - a form squeezed by the sidebar stacks just like on a phone.
const SECTION_GRID_CLASS: Record<number, string> = {
  2: '@lg:grid-cols-2',
  3: '@lg:grid-cols-2 @3xl:grid-cols-3',
  4: '@lg:grid-cols-2 @4xl:grid-cols-4',
}

function sectionGridClass(section: LayoutSection): string {
  return SECTION_GRID_CLASS[Math.min(section.columns.length, 4)] ?? ''
}

// A collapsible section starts folded when every field in it is empty. Decided
// once per document (not live, so clearing a field doesn't fold the section
// under the cursor); the user's own toggles stick.
const collapsedSections = ref<Record<string, boolean>>({})

function isFilled(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0
  return value !== null && value !== undefined && value !== '' && value !== false && value !== 0
}

watch(
  [parsedLayout, () => props.modelValue?.name],
  () => {
    const state: Record<string, boolean> = {}
    for (const section of parsedLayout.value.flatMap((tab) => tab.sections)) {
      if (!section.collapsible) continue
      state[section._fieldname] = !section.columns.some((col) =>
        col.some((f) => isFilled(props.modelValue?.[f.fieldname])),
      )
    }
    collapsedSections.value = state
  },
  { immediate: true },
)

function isCollapsed(section: LayoutSection): boolean {
  return section.collapsible && !!collapsedSections.value[section._fieldname]
}

function toggleSection(section: LayoutSection) {
  if (section.collapsible) collapsedSections.value[section._fieldname] = !isCollapsed(section)
}
</script>

<template>
  <Tabs v-model="currentTab" class="w-full min-w-0">
    <!-- Tab navigation (hidden when there's nothing worth switching between) -->
    <div v-if="hasTabs" class="flex items-center gap-1 mb-4">
      <Button v-if="canScrollLeft" variant="ghost" size="icon" class="size-7 shrink-0" @click="scrollTabsBy(-160)">
        <ChevronLeft class="size-4" />
      </Button>
      <TabsList ref="tabsListRef" class="flex-1 min-w-0 justify-start overflow-x-auto [scrollbar-width:none]" @scroll="updateTabScrollState">
        <TabsTrigger v-for="{ tab } in layout" :key="tab._fieldname" :value="tab._fieldname" class="flex-none px-3">
          <AppIcon v-if="tab._field?.icon" :icon="tab._field.icon" class="size-3.5 shrink-0" />
          <span>{{ tab.label || t('Main') }}</span>
        </TabsTrigger>
      </TabsList>
      <Button v-if="canScrollRight" variant="ghost" size="icon" class="size-7 shrink-0" @click="scrollTabsBy(160)">
        <ChevronRight class="size-4" />
      </Button>
    </div>

    <!-- Sections -->
    <TabsContent v-for="{ tab, component, sections } in layout" :key="tab._fieldname" :value="tab._fieldname"
      class="mt-0 flex flex-col gap-4 focus-visible:ring-0">
      <!-- Connections panel, when this Tab has `show_connections` set -->
      <DocConnections
        v-if="connectionsTabId === tab._fieldname"
        :dt="doctype"
        :document="modelValue"
        :workspace="workspace"
        @create-new="onCreateNew"
      />
      <!-- Support for custom tab components (e.g. Designer, Workflow graph) -->
      <component :is="component" v-if="component" :doctype="doctype"
        :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" />
      <template v-else>
        <Collapsible v-for="section in sections" :key="section._fieldname"
          :open="!isCollapsed(section)" :disabled="!section.collapsible"
          :class="[section.label ? 'form-section' : '', '@container mb-3 last:mb-0']"
          @update:open="toggleSection(section)">

          <!-- Section header -->
          <CollapsibleTrigger v-if="section.label" class="form-section-header w-full text-left enabled:cursor-pointer">
            <ChevronDown v-if="section.collapsible"
              class="size-3.5 text-muted-foreground transition-transform duration-200"
              :class="{ '-rotate-90': isCollapsed(section) }" />
            <span>{{ section.label }}</span>
          </CollapsibleTrigger>

          <!-- Fields layout -->
          <CollapsibleContent
            :class="section.collapsible && 'overflow-hidden data-open:animate-collapsible-down data-closed:animate-collapsible-up'">
            <div class="grid grid-cols-1 gap-x-5 gap-y-5"
              :class="[section.label ? 'form-section-body' : '', sectionGridClass(section)]">
              <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-3 min-w-0">
                <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname"
                  class="relative group" @focusin="emit('field-focus', f.fieldname)"
                  @focusout="emit('field-blur', f.fieldname)">

                  <!-- Field lock badge -->
                  <div v-if="fieldLocks?.[f.fieldname]"
                    class="mb-1 flex items-center gap-1 self-start rounded-full px-2 py-0.5 font-semibold text-white shadow-sm ring-2 ring-background"
                    :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                    <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                    <span>{{ t('Editing...') }}</span>
                  </div>

                  <FieldRenderer :field="mergedField(f)" :model-value="modelValue[f.fieldname]"
                    :disabled="disabled || f.read_only || !!fieldLocks?.[f.fieldname]" :error="errors?.[f.fieldname]"
                    :doc-values="modelValue" @update:model-value="update(f.fieldname, $event)"
                    @create-new="onCreateNew" @table-selection-change="onTableSelectionChange" />
                </div>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </template>
    </TabsContent>
  </Tabs>
</template>

