<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useBuilderStore } from '@/stores/builder'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Input } from '@/components/ui/input'
import { FormField } from '@/components/ui/form-field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const builder = useBuilderStore()

const field = computed(() => builder.selectedField)

const doctypeList = ref<DocTypeSummary[]>([])
const childDoctypes = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try {
    doctypeList.value = await metaApi.list()
    childDoctypes.value = doctypeList.value.filter((d) => d.is_child)
  } catch {}
})

function updateField(key: string, val: unknown) {
  if (!builder.selectedFieldName) return
  builder.updateField(builder.selectedFieldName, { [key]: val } as Record<string, unknown>)
}

function updateDocType(key: string, val: unknown) {
  builder.updateDocType({ [key]: val } as Record<string, unknown>)
}

const titleFieldOptions = computed(() =>
  (builder.doctype?.fields ?? [])
    .filter((f) => !['Section', 'Column', 'Tab'].includes(f.fieldtype))
    .map((f) => f.fieldname)
)

const doctypeOptionsList = computed(() => doctypeList.value.map((d) => d.name))
const childDoctypeOptionsList = computed(() => childDoctypes.value.map((d) => d.name))

const isLayoutField = computed(() =>
  field.value ? ['Section', 'Column', 'Tab'].includes(field.value.fieldtype) : false
)
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-[--grunt-border] bg-[--grunt-surface-secondary]">
    <!-- No selection: DocType props -->
    <template v-if="!field && builder.doctype">
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">DocType</p>
      <div class="flex flex-col gap-3">
        <FormField label="Label">
          <template #default="{ id }">
            <Input :id="id" :model-value="builder.doctype.label" @update:model-value="updateDocType('label', $event)" />
          </template>
        </FormField>
        <FormField label="Module">
          <template #default="{ id }">
            <Input :id="id" :model-value="builder.doctype.module" @update:model-value="updateDocType('module', $event)" />
          </template>
        </FormField>
        <FormField label="Title Field">
          <template #default="{ id }">
            <Select :model-value="builder.doctype.title_field ?? ''" @update:model-value="updateDocType('title_field', $event || undefined)">
              <SelectTrigger :id="id">
                <SelectValue placeholder="— оберіть —" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="opt in titleFieldOptions" :key="opt" :value="opt">{{ opt }}</SelectItem>
              </SelectContent>
            </Select>
          </template>
        </FormField>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!builder.doctype.is_submittable" class="rounded" @change="updateDocType('is_submittable', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm text-[--grunt-text-primary]">Is Submittable</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!builder.doctype.is_child" class="rounded" @change="updateDocType('is_child', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm text-[--grunt-text-primary]">Child DocType</span>
        </label>
        <RouterLink
          v-if="builder.doctype.is_submittable"
          :to="`/studio/${builder.doctype.name}/workflow`"
          class="flex items-center gap-1.5 text-sm text-[--grunt-primary] hover:underline mt-1"
        >
          &#9889; Workflow &rarr;
        </RouterLink>
      </div>
    </template>

    <!-- Tab field selected -->
    <template v-else-if="field && field.fieldtype === 'Tab'">
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">Tab</p>
      <div class="flex flex-col gap-3">
        <FormField label="Label *" required>
          <template #default="{ id }">
            <Input :id="id" :model-value="field.label" @update:model-value="updateField('label', $event)" />
          </template>
        </FormField>
        <FormField label="Fieldname">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.fieldname" disabled />
          </template>
        </FormField>
      </div>
    </template>

    <!-- Section field selected -->
    <template v-else-if="field && field.fieldtype === 'Section'">
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">Section</p>
      <div class="flex flex-col gap-3">
        <FormField label="Label">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.label" @update:model-value="updateField('label', $event)" />
          </template>
        </FormField>
        <FormField label="Fieldname">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.fieldname" disabled />
          </template>
        </FormField>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.collapsible" class="rounded" @change="updateField('collapsible', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">Collapsible</span>
        </label>
        <FormField label="Depends On">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
          </template>
        </FormField>
      </div>
    </template>

    <!-- Regular field selected -->
    <template v-else-if="field && !isLayoutField">
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">Field: {{ field.fieldtype }}</p>

      <!-- Core -->
      <div class="flex flex-col gap-3 mb-5">
        <FormField label="Label *" required>
          <template #default="{ id }">
            <Input :id="id" :model-value="field.label" @update:model-value="updateField('label', $event)" />
          </template>
        </FormField>
        <FormField label="Fieldname *">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.fieldname" @update:model-value="updateField('fieldname', $event)" />
          </template>
        </FormField>
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

      <!-- Display -->
      <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-3">Display</p>
      <div class="flex flex-col gap-3 mb-5">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.in_list_view" class="rounded" @change="updateField('in_list_view', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">In List View</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" :checked="!!field.in_filter" class="rounded" @change="updateField('in_filter', ($event.target as HTMLInputElement).checked)" />
          <span class="text-sm">In Filter</span>
        </label>
        <FormField label="Description">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.description ?? ''" @update:model-value="updateField('description', $event || undefined)" />
          </template>
        </FormField>
        <FormField label="Placeholder">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.placeholder ?? ''" @update:model-value="updateField('placeholder', $event || undefined)" />
          </template>
        </FormField>
        <FormField label="Depends On">
          <template #default="{ id }">
            <Input :id="id" :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
          </template>
        </FormField>
      </div>

      <!-- Type-specific -->
      <template v-if="field.fieldtype === 'Select'">
        <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-2">Options</p>
        <textarea
          :value="field.options ?? ''"
          rows="5"
          placeholder="Each option on a new line"
          class="w-full text-sm border border-[--grunt-border] rounded-[--grunt-radius-sm] px-2 py-1.5 focus:outline-none focus:border-[--grunt-primary]"
          @input="updateField('options', ($event.target as HTMLTextAreaElement).value)"
        />
      </template>

      <template v-if="field.fieldtype === 'Link'">
        <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-2">Linked DocType *</p>
        <Select :model-value="field.options ?? ''" @update:model-value="updateField('options', $event)">
          <SelectTrigger>
            <SelectValue placeholder="— оберіть —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in doctypeOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </template>

      <template v-if="field.fieldtype === 'Table'">
        <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-2">Child DocType *</p>
        <Select :model-value="field.options ?? ''" @update:model-value="updateField('options', $event)">
          <SelectTrigger>
            <SelectValue placeholder="— оберіть —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in childDoctypeOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </template>

      <template v-if="['Int', 'Float'].includes(field.fieldtype)">
        <div class="flex gap-2 mt-3">
          <FormField label="Min Value">
            <template #default="{ id }">
              <Input :id="id" :model-value="String(field.min_value ?? '')" type="number" @update:model-value="updateField('min_value', $event ? Number($event) : undefined)" />
            </template>
          </FormField>
          <FormField label="Max Value">
            <template #default="{ id }">
              <Input :id="id" :model-value="String(field.max_value ?? '')" type="number" @update:model-value="updateField('max_value', $event ? Number($event) : undefined)" />
            </template>
          </FormField>
        </div>
      </template>
    </template>

    <div v-else class="flex items-center justify-center h-32 text-[--grunt-text-muted] text-sm">
      Select a field to edit properties
    </div>
  </div>
</template>
