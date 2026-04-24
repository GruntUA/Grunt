<script setup lang="ts">
import { computed, ref, shallowRef, defineAsyncComponent, type Component } from 'vue'
import type { DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { LayoutSection } from '@/core/composables/useFormLayout'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import { ChevronDown } from '@lucide/vue'
import FieldRenderer from './FieldRenderer.vue'
import DesignerTab from '../../pages/studio/builder/DesignerTab.vue'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, unknown>
  activeTab?: string
  disabled?: boolean
  errors?: Record<string, string>
  overrides?: Record<string, boolean>
  reqdOverrides?: Record<string, boolean>
  fieldLocks?: Record<string, PresenceUser>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  'update:activeTab': [value: string]
  'field-focus': [fieldname: string]
  'field-blur': [fieldname: string]
  'create-new': [doctype: string, preset: string, fieldname: string]
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
}

function getCustomTabComponent(name: string): Component | null {
  return customTabComponents[name] ?? null
}


function update(fieldname: string, val: unknown) {
  emit('update:modelValue', { ...props.modelValue, [fieldname]: val })
}

function toggleSection(section: LayoutSection) {
  if (section.collapsible) section.collapsed = !section.collapsed
}
</script>

<template>
  <Tabs v-if="hasTabs" v-model:value="currentTab" class="w-full overflow-hidden">
    <!-- Tab navigation -->
    <TabList 
      scrollable 
      variant="underline" 
      class="mb-6 h-auto border-b border-border px-2"
      :pt="{
        prevButton: { class: 'bg-background hover:bg-muted text-primary shadow-sm border-r border-border/40 w-10 flex items-center justify-center' },
        nextButton: { class: 'bg-background hover:bg-muted text-primary shadow-sm border-l border-border/40 w-10 flex items-center justify-center' }
      }"
    >
      <Tab v-for="(tab, ti) in layout" :key="ti" :value="tab.label || 'Main'" variant="underline" class="flex items-center gap-1.5 px-4 h-10">
        <component :is="getTabIcon(tab._field?.icon)" v-if="tab._field?.icon" class="size-3.5 shrink-0" />
        <span class="text-sm font-medium tracking-wide">{{ tab.label || 'Main' }}</span>
      </Tab>
    </TabList>

    <!-- Sections -->
    <TabPanels>
      <TabPanel v-for="(tab, ti) in layout" :key="ti" :value="tab.label || 'Main'"
        class="mt-0 flex flex-col gap-3 focus-visible:ring-0">
        <!-- Support for custom tab components (e.g. Studio Designer) -->
        <template v-if="tab._field?.experimental_component">
          <component :is="getCustomTabComponent(tab._field.experimental_component)" :doctype="doctype"
            :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" />
        </template>
        <template v-else>
          <div v-for="(section, si) in tab.sections" :key="si" :class="section.label ? 'form-section' : ''">

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
                class="grid grid-cols-1 gap-y-4 md:gap-x-6"
                :style="section.columns.length > 1 ? `grid-template-columns: repeat(${Math.min(section.columns.length, 4)}, minmax(0, 1fr))` : ''">
                <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-4 min-w-0">
                  <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname" class="relative group"
                    @focusin="emit('field-focus', f.fieldname)" @focusout="emit('field-blur', f.fieldname)">

                    <!-- Field lock badge -->
                    <div v-if="fieldLocks?.[f.fieldname]"
                      class="mb-1 flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-[10px] font-bold text-white shadow-sm ring-2 ring-background"
                      :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                      <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                      <span>редагує...</span>
                    </div>

                    <FieldRenderer
                      :field="reqdOverrides?.[f.fieldname] !== undefined ? { ...f, required: reqdOverrides[f.fieldname] } : f"
                      :model-value="modelValue[f.fieldname]"
                      :disabled="disabled || f.read_only || !!fieldLocks?.[f.fieldname]" :error="errors?.[f.fieldname]"
                      :doc-values="modelValue" @update:model-value="update(f.fieldname, $event)"
                      @create-new="(doctype, preset, fieldname) => emit('create-new', doctype, preset, fieldname)" />
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </template>
      </TabPanel>
    </TabPanels>
  </Tabs>

  <!-- Non-tabbed layout fallback (or single tab with no label) -->
  <template v-else v-for="(tab, ti) in layout" :key="ti">
    <div class="flex flex-col gap-3">
      <div v-for="(section, si) in tab.sections" :key="si"
        :class="section.label ? 'form-section' : ''">
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
            class="grid grid-cols-1 gap-y-4 md:gap-x-6"
            :style="section.columns.length > 1 ? `grid-template-columns: repeat(${Math.min(section.columns.length, 4)}, minmax(0, 1fr))` : ''">
            <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-4 min-w-0">
              <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname"
                class="relative group" @focusin="emit('field-focus', f.fieldname)"
                @focusout="emit('field-blur', f.fieldname)">
                <div v-if="fieldLocks?.[f.fieldname]"
                  class="mb-1 flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-[10px] font-bold text-white shadow-sm ring-2 ring-background"
                  :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                  <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                  <span>редагує...</span>
                </div>
                <FieldRenderer
                  :field="reqdOverrides?.[f.fieldname] !== undefined ? { ...f, required: reqdOverrides[f.fieldname] } : f"
                  :model-value="modelValue[f.fieldname]"
                  :disabled="disabled || f.read_only || !!fieldLocks?.[f.fieldname]" :error="errors?.[f.fieldname]"
                  :doc-values="modelValue"
                  @update:model-value="update(f.fieldname, $event)"
                  @create-new="(doctype, preset, fieldname) => emit('create-new', doctype, preset, fieldname)"
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
