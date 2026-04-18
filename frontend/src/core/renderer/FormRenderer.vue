<script setup lang="ts">
import { computed, ref, shallowRef, type Component } from 'vue'
import type { DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { LayoutSection } from '@/core/composables/useFormLayout'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import { ChevronDown } from '@lucide/vue'
import FieldRenderer from './FieldRenderer.vue'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, unknown>
  disabled?: boolean
  errors?: Record<string, string>
  overrides?: Record<string, boolean>
  reqdOverrides?: Record<string, boolean>
  fieldLocks?: Record<string, PresenceUser>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  'field-focus': [fieldname: string]
  'field-blur': [fieldname: string]
  'create-new': [doctype: string, preset: string, fieldname: string]
}>()

const layout = computed(() => parseLayout(props.doctype.fields))
const hasTabs = computed(() => layout.value.length > 1 || layout.value[0]?.label !== '')
const activeTab = ref(0)

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


function update(fieldname: string, val: unknown) {
  emit('update:modelValue', { ...props.modelValue, [fieldname]: val })
}

function toggleSection(section: LayoutSection) {
  if (section.collapsible) section.collapsed = !section.collapsed
}
</script>

<template>
  <!-- Tab navigation -->
  <div v-if="hasTabs" class="flex gap-0 border-b border-border mb-6 -mx-6 px-6 overflow-x-auto">
    <button v-for="(tab, ti) in layout" :key="ti" type="button"
      class="inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap" :class="activeTab === ti
        ? 'border-primary text-primary'
        : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'"
      @click="activeTab = ti">
      <component :is="getTabIcon(tab._field?.icon)" v-if="tab._field?.icon" class="size-3.5 shrink-0" />
      {{ tab.label || 'Main' }}</button>
  </div>

  <!-- Sections -->
  <template v-for="(tab, ti) in layout" :key="ti">
    <div v-show="activeTab === ti" class="flex flex-col gap-3">
      <div v-for="(section, si) in tab.sections" :key="si"
        :class="section.label ? 'form-section' : ''">

        <!-- Section header (Frappe-style card header) -->
        <div v-if="section.label" class="form-section-header"
          :class="{ 'cursor-pointer select-none': section.collapsible }"
          @click="toggleSection(section)">
          <ChevronDown v-if="section.collapsible"
            class="size-3.5 text-muted-foreground transition-transform duration-200"
            :class="{ '-rotate-90': section.collapsed }" />
          <span>{{ section.label }}</span>
        </div>

        <!-- Fields layout -->
        <Transition name="section">
          <div v-if="!section.collapsed"
            :class="section.label ? 'form-section-body' : ''"
            class="grid grid-cols-1 gap-y-4 md:gap-x-6"
            :style="section.columns.length > 1 ? `grid-template-columns: repeat(${Math.min(section.columns.length, 4)}, minmax(0, 1fr))` : ''">
            <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-4 min-w-0">
              <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname"
                class="relative group" @focusin="emit('field-focus', f.fieldname)"
                @focusout="emit('field-blur', f.fieldname)">

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
</style>
