<script setup lang="ts">
import { computed, shallowRef, type Component } from 'vue'
import type { DocField, DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { LayoutSection, LayoutTab } from '@/core/composables/useFormLayout'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import { ChevronDown } from '@lucide/vue'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import FieldRenderer from './FieldRenderer.vue'
import DesignerTab from '../../pages/studio/builder/DesignerTab.vue'
import ViewsTab from '../../pages/studio/builder/tabs/ViewsTab.vue'

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

const lucideIcons = shallowRef<Record<string, Component>>({})
let _iconsLoaded = false
function getTabIcon(name: string | undefined): Component | null {
  if (!name) return null
  if (!_iconsLoaded) {
    _iconsLoaded = true
    import('@lucide/vue').then((lib) => { lucideIcons.value = lib as unknown as Record<string, Component> })
  }
  const pascal = name.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] ?? null) as Component | null
}

const customTabComponents: Record<string, Component> = {
  DesignerTab,
  ViewsTab,
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
  <Tabs v-if="hasTabs" v-model="currentTab" class="w-full overflow-hidden">
    <!-- Tab navigation -->
    <div class="relative mb-4">
      <TabsList
        class="h-auto w-full justify-start rounded-none border-b border-border bg-transparent px-2 overflow-x-auto scrollbar-none sticky top-0 z-10 bg-background/95 backdrop-blur"
      >
        <TabsTrigger
          v-for="(tab, ti) in layout"
          :key="ti"
          :value="tab.label || 'Main'"
          class="flex items-center gap-1.5 px-3 h-9 whitespace-nowrap rounded-t-md rounded-b-none border-0 shadow-none transition-colors duration-150 data-[state=active]:bg-muted/60 data-[state=active]:border-b-2 data-[state=active]:border-primary hover:bg-muted/30"
        >
          <component
            v-if="tab._field?.icon && getTabIcon(tab._field?.icon)"
            :is="getTabIcon(tab._field?.icon)"
            class="size-3.5 shrink-0"
          />
          <span class="text-[13px] font-semibold tracking-wide">{{ tab.label || 'Main' }}</span>
        </TabsTrigger>
      </TabsList>
      <div class="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-background/95 to-transparent" />
      <div class="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-background/95 to-transparent" />
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
          <div v-for="(section, si) in getVisibleSections(tab)" :key="si" :class="[section.label ? 'form-section' : '', 'mb-3 last:mb-0']">

            <!-- Section header (Frappe-style card header) -->
            <div v-if="section.label" class="form-section-header"
              :class="{ 'cursor-pointer select-none': section.collapsible }" @click="toggleSection(section)">
              <ChevronDown v-if="section.collapsible" class="size-3.5 text-muted-foreground transition-transform duration-200"
                :class="{ '-rotate-90': section.collapsed }" />
              <span>{{ section.label }}</span>
            </div>

            <!-- Fields layout -->
            <Transition name="section">
              <div v-if="!section.collapsed" :class="section.label ? 'form-section-body' : ''"
                class="grid grid-cols-1 gap-y-5 md:gap-x-5"
                :style="section.columns.length > 1 ? `grid-template-columns: repeat(${Math.min(section.columns.length, 4)}, minmax(0, 1fr))` : ''">
                <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-3 min-w-0">
                  <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname" class="relative group"
                    @focusin="emit('field-focus', f.fieldname)" @focusout="emit('field-blur', f.fieldname)">

                    <!-- Field lock badge -->
                    <div v-if="fieldLocks?.[f.fieldname]"
                      class="mb-1 flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-[10px] font-bold text-white shadow-sm ring-2 ring-background"
                      :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                      <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                      <span>editing...</span>
                    </div>

                    <FieldRenderer
                      :field="mergedField(f)"
                      :model-value="modelValue[f.fieldname]"
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

  <!-- Non-tabbed layout fallback (or single tab with no label) -->
  <template v-else v-for="(tab, ti) in layout" :key="ti">
    <div class="flex flex-col gap-4">
      <div v-for="(section, si) in getVisibleSections(tab)" :key="si"
        :class="[section.label ? 'form-section' : '', 'mb-3 last:mb-0']">
        <!-- ... same content as inside TabPanel above ... -->
        <div v-if="section.label" class="form-section-header"
          :class="{ 'cursor-pointer select-none': section.collapsible }"
          @click="toggleSection(section)">
          <ChevronDown v-if="section.collapsible"
            class="size-3.5 text-muted-foreground transition-transform duration-200"
            :class="{ '-rotate-90': section.collapsed }" />
          <span>{{ section.label }}</span>
        </div>

        <Transition name="section">
          <div v-if="!section.collapsed"
            :class="section.label ? 'form-section-body' : ''"
            class="grid grid-cols-1 gap-y-5 md:gap-x-5"
            :style="section.columns.length > 1 ? `grid-template-columns: repeat(${Math.min(section.columns.length, 4)}, minmax(0, 1fr))` : ''">
            <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-3 min-w-0">
              <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname"
                class="relative group" @focusin="emit('field-focus', f.fieldname)"
                @focusout="emit('field-blur', f.fieldname)">
                <div v-if="fieldLocks?.[f.fieldname]"
                  class="mb-1 flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-[10px] font-bold text-white shadow-sm ring-2 ring-background"
                  :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                  <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                  <span>editing...</span>
                </div>
                <FieldRenderer
                  :field="mergedField(f)"
                  :model-value="modelValue[f.fieldname]"
                  :disabled="disabled || f.read_only || !!fieldLocks?.[f.fieldname]" :error="errors?.[f.fieldname]"
                  :doc-values="modelValue"
                  @update:model-value="update(f.fieldname, $event)"
                  @create-new="(doctype, preset, fieldname) => emit('create-new', doctype, preset, fieldname)"
                  @table-selection-change="(fieldname, rowNames) => emit('table-selection-change', { fieldname, rowNames })"
                />
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </template>
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
