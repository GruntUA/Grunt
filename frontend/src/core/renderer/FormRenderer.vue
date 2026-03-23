<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { LayoutSection } from '@/core/composables/useFormLayout'
import FieldRenderer from './FieldRenderer.vue'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, unknown>
  disabled?: boolean
  errors?: Record<string, string>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()

const layout = computed(() => parseLayout(props.doctype.fields))
const hasTabs = computed(() => layout.value.length > 1 || layout.value[0]?.label !== '')
const activeTab = ref(0)

function colClass(count: number): string {
  return ['form-grid-1', 'form-grid-2', 'form-grid-3', 'form-grid-4'][count - 1] ?? 'form-grid-1'
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
  <div v-if="hasTabs" class="flex gap-0 border-b border-[--grunt-border] mb-6 -mx-6 px-6 overflow-x-auto">
    <button
      v-for="(tab, ti) in layout"
      :key="ti"
      type="button"
      class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
      :class="activeTab === ti
        ? 'border-[--grunt-primary] text-[--grunt-primary]'
        : 'border-transparent text-[--grunt-text-secondary] hover:text-[--grunt-text-primary]'"
      @click="activeTab = ti"
    >{{ tab.label || 'Main' }}</button>
  </div>

  <!-- Sections -->
  <template v-for="(tab, ti) in layout" :key="ti">
    <div v-show="activeTab === ti" class="flex flex-col gap-6">
      <div v-for="(section, si) in tab.sections" :key="si">
        <!-- Section header -->
        <div
          v-if="section.label"
          class="flex items-center gap-2 mb-3 cursor-pointer"
          :class="{ 'cursor-pointer select-none': section.collapsible }"
          @click="toggleSection(section)"
        >
          <span class="text-xs font-semibold uppercase tracking-wide text-[--grunt-text-secondary]">{{ section.label }}</span>
          <div class="flex-1 h-px bg-[--grunt-border]" />
          <span v-if="section.collapsible" class="text-[--grunt-text-muted] text-xs">{{ section.collapsed ? '▶' : '▼' }}</span>
        </div>

        <!-- Fields grid -->
        <div v-if="!section.collapsed" :class="colClass(section.columns.length)" class="gap-4">
          <div v-for="(col, ci) in section.columns" :key="ci" class="flex flex-col gap-4">
            <FieldRenderer
              v-for="f in col"
              :key="f.fieldname"
              :field="f"
              :model-value="modelValue[f.fieldname]"
              :disabled="disabled || f.read_only"
              :error="errors?.[f.fieldname]"
              :doc-values="modelValue"
              @update:model-value="update(f.fieldname, $event)"
            />
          </div>
        </div>
      </div>
    </div>
  </template>
</template>

<style scoped>
.form-grid-1 { display: grid; grid-template-columns: 1fr; }
.form-grid-2 { display: grid; grid-template-columns: 1fr; }
.form-grid-3 { display: grid; grid-template-columns: 1fr; }
.form-grid-4 { display: grid; grid-template-columns: 1fr; }

@media (min-width: 768px) {
  .form-grid-2 { grid-template-columns: 1fr 1fr; }
  .form-grid-3 { grid-template-columns: 1fr 1fr; }
  .form-grid-4 { grid-template-columns: 1fr 1fr; }
}

@media (min-width: 1024px) {
  .form-grid-3 { grid-template-columns: 1fr 1fr 1fr; }
  .form-grid-4 { grid-template-columns: repeat(3, 1fr); }
}

@media (min-width: 1280px) {
  .form-grid-4 { grid-template-columns: repeat(4, 1fr); }
}
</style>
