<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useBuilderStore } from '@/stores/builder'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import GInput from '@/components/ui/GInput.vue'
import GSelect from '@/components/ui/GSelect.vue'

const builder = useBuilderStore()

const field = computed(() =>
  builder.selectedFieldIndex !== null
    ? builder.doctype?.fields[builder.selectedFieldIndex] ?? null
    : null
)

const doctypeList = ref<DocTypeSummary[]>([])
const childDoctypes = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try {
    doctypeList.value = await metaApi.list()
    childDoctypes.value = doctypeList.value.filter((d) => d.is_child)
  } catch {}
})

function updateField(key: string, val: unknown) {
  if (builder.selectedFieldIndex === null) return
  builder.updateField(builder.selectedFieldIndex, { [key]: val } as Record<string, unknown>)
}

function updateDocType(key: string, val: unknown) {
  builder.updateDocType({ [key]: val } as Record<string, unknown>)
}

const titleFieldOptions = computed(() =>
  (builder.doctype?.fields ?? [])
    .filter((f) => !['Section', 'Column', 'Tab'].includes(f.fieldtype))
    .map((f) => f.fieldname)
    .join('\n')
)

const doctypeOptions = computed(() => doctypeList.value.map((d) => d.name).join('\n'))
const childDoctypeOptions = computed(() => childDoctypes.value.map((d) => d.name).join('\n'))
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-[--grunt-border] bg-[--grunt-surface-secondary]">
    <!-- No selection: DocType props -->
    <template v-if="!field && builder.doctype">
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">DocType</p>
      <div class="flex flex-col gap-3">
        <GInput :model-value="builder.doctype.label" label="Label" @update:model-value="updateDocType('label', $event)" />
        <GInput :model-value="builder.doctype.module" label="Модуль" @update:model-value="updateDocType('module', $event)" />
        <GSelect :model-value="builder.doctype.title_field ?? ''" label="Title Field" :options="titleFieldOptions" @update:model-value="updateDocType('title_field', $event || undefined)" />
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!builder.doctype.is_submittable" class="rounded" @change="updateDocType('is_submittable', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm text-[--grunt-text-primary]">Is Submittable</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!builder.doctype.is_child" class="rounded" @change="updateDocType('is_child', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm text-[--grunt-text-primary]">Child DocType</span>
        </label>
        <!-- Workflow link for submittable doctypes -->
        <RouterLink
          v-if="builder.doctype.is_submittable"
          :to="`/studio/${builder.doctype.name}/workflow`"
          class="flex items-center gap-1.5 text-sm text-[--grunt-primary] hover:underline mt-1"
        >
          &#9889; Налаштувати Workflow &rarr;
        </RouterLink>
      </div>
    </template>

    <!-- Field selected -->
    <template v-else-if="field">
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">Поле: {{ field.fieldtype }}</p>

      <!-- Основне -->
      <div class="flex flex-col gap-3 mb-5">
        <GInput :model-value="field.label" label="Label *" required @update:model-value="updateField('label', $event)" />
        <GInput :model-value="field.fieldname" label="Fieldname *" @update:model-value="updateField('fieldname', $event)" />
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.required" class="rounded" @change="updateField('required', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">Required</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.hidden" class="rounded" @change="updateField('hidden', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">Hidden</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.read_only" class="rounded" @change="updateField('read_only', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">Read Only</span>
        </label>
      </div>

      <!-- Відображення -->
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-3">Відображення</p>
      <div class="flex flex-col gap-3 mb-5">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.in_list_view" class="rounded" @change="updateField('in_list_view', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">In List View</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.in_filter" class="rounded" @change="updateField('in_filter', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">In Filter</span>
        </label>
        <GInput :model-value="field.description ?? ''" label="Description" @update:model-value="updateField('description', $event || undefined)" />
        <GInput :model-value="field.placeholder ?? ''" label="Placeholder" @update:model-value="updateField('placeholder', $event || undefined)" />
        <GInput :model-value="field.depends_on ?? ''" label="Depends On" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
      </div>

      <!-- Тип-специфічні -->
      <template v-if="field.fieldtype === 'Select'">
        <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-2">Options</p>
        <textarea
          :value="field.options ?? ''"
          rows="5"
          placeholder="Кожен варіант з нового рядка"
          class="w-full text-sm border border-[--grunt-border] rounded-[--grunt-radius-sm] px-2 py-1.5 focus:outline-none focus:border-[--grunt-primary]"
          @input="updateField('options', ($event.target as HTMLTextAreaElement).value)"
        />
      </template>

      <template v-if="field.fieldtype === 'Link'">
        <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-2">Linked DocType *</p>
        <GSelect :model-value="field.options ?? ''" :options="doctypeOptions" @update:model-value="updateField('options', $event)" />
      </template>

      <template v-if="field.fieldtype === 'Table'">
        <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-2">Child DocType *</p>
        <GSelect :model-value="field.options ?? ''" :options="childDoctypeOptions" @update:model-value="updateField('options', $event)" />
      </template>

      <template v-if="['Int', 'Float'].includes(field.fieldtype)">
        <div class="flex gap-2 mt-3">
          <GInput :model-value="String(field.min_value ?? '')" label="Min Value" type="number" @update:model-value="updateField('min_value', $event ? Number($event) : undefined)" />
          <GInput :model-value="String(field.max_value ?? '')" label="Max Value" type="number" @update:model-value="updateField('max_value', $event ? Number($event) : undefined)" />
        </div>
      </template>
    </template>

    <div v-else class="flex items-center justify-center h-32 text-[--grunt-text-muted] text-sm">
      Виберіть поле для редагування
    </div>
  </div>
</template>
