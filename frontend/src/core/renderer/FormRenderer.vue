<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { LayoutSection } from '@/core/composables/useFormLayout'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import { ChevronDown } from 'lucide-vue-next'
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
}>()

const layout = computed(() => parseLayout(props.doctype.fields))
const hasTabs = computed(() => layout.value.length > 1 || layout.value[0]?.label !== '')
const activeTab = ref(0)

const colSpanMap: Record<number, string> = {
  1: 'md:col-span-1', 2: 'md:col-span-2', 3: 'md:col-span-3', 4: 'md:col-span-4',
  5: 'md:col-span-5', 6: 'md:col-span-6', 7: 'md:col-span-7', 8: 'md:col-span-8',
  9: 'md:col-span-9', 10: 'md:col-span-10', 11: 'md:col-span-11', 12: 'md:col-span-12',
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
      class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap" :class="activeTab === ti
        ? 'border-primary text-primary'
        : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'"
      @click="activeTab = ti">{{ tab.label || 'Main' }}</button>
  </div>

  <!-- Sections -->
  <template v-for="(tab, ti) in layout" :key="ti">
    <div v-show="activeTab === ti" class="flex flex-col gap-6">
      <div v-for="(section, si) in tab.sections" :key="si">
        <!-- Section header -->
        <div v-if="section.label" class="flex items-center gap-2 mb-4"
          :class="{ 'cursor-pointer select-none': section.collapsible }" @click="toggleSection(section)">
          <ChevronDown v-if="section.collapsible" class="size-4 text-muted-foreground transition-transform duration-200"
            :class="{ '-rotate-90': section.collapsed }" />
          <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">{{ section.label }}</span>
          <div class="flex-1 h-px bg-border" />
        </div>

        <!-- Fields layout -->
        <Transition name="section">
          <div v-if="!section.collapsed" class="grid grid-cols-1 gap-y-4 md:gap-x-8" :class="[
            section.columns.length === 2 ? 'md:grid-cols-2' : '',
            section.columns.length === 3 ? 'md:grid-cols-3' : '',
            section.columns.length >= 4 ? 'md:grid-cols-4' : '',
          ]">
            <div v-for="(col, ci) in section.columns" :key="ci" class="flex-1 flex flex-col gap-4 min-w-0">
              <div v-for="f in col" v-show="overrides?.[f.fieldname] !== false" :key="f.fieldname"
                class="grid grid-cols-12 gap-2 relative group" @focusin="emit('field-focus', f.fieldname)"
                @focusout="emit('field-blur', f.fieldname)">

                <!-- Field label & lock container -->
                <div class="col-span-12 flex items-center justify-between gap-2">
                  <!-- Field lock badge -->
                  <div v-if="fieldLocks?.[f.fieldname]"
                    class="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold text-white shadow-sm ring-2 ring-background"
                    :style="{ backgroundColor: fieldLocks[f.fieldname].color }">
                    <span class="opacity-80">{{ initials(fieldLocks[f.fieldname].full_name) }}</span>
                    <span>редагує...</span>
                  </div>
                </div>

                <div :class="f.columns ? colSpanMap[f.columns] : 'col-span-12'">
                  <FieldRenderer
                    :field="reqdOverrides?.[f.fieldname] !== undefined ? { ...f, required: reqdOverrides[f.fieldname] } : f"
                    :model-value="modelValue[f.fieldname]"
                    :disabled="disabled || f.read_only || !!fieldLocks?.[f.fieldname]" :error="errors?.[f.fieldname]"
                    :doc-values="modelValue" @update:model-value="update(f.fieldname, $event)" />
                </div>
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
