<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'

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

const doctypeOptionsList = computed(() => doctypeList.value.map((d) => d.name))
const childDoctypeOptionsList = computed(() => childDoctypes.value.map((d) => d.name))

const isLayoutField = computed(() =>
  field.value ? ['Section', 'Column', 'Tab'].includes(field.value.fieldtype) : false
)
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-border bg-card">
    <!-- Tab field selected -->
    <template v-if="field && field.fieldtype === 'Tab'">
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">Tab</p>
      <div class="flex flex-col gap-3">
        <div class="space-y-1.5">
          <Label class="text-sm">Label *</Label>
          <Input :model-value="field.label" @update:model-value="updateField('label', $event)" />
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm text-muted-foreground">Fieldname</Label>
          <Input :model-value="field.fieldname" disabled />
        </div>
      </div>
    </template>

    <!-- Section field selected -->
    <template v-else-if="field && field.fieldtype === 'Section'">
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">Section</p>
      <div class="flex flex-col gap-3">
        <div class="space-y-1.5">
          <Label class="text-sm">Label</Label>
          <Input :model-value="field.label" @update:model-value="updateField('label', $event)" />
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm text-muted-foreground">Fieldname</Label>
          <Input :model-value="field.fieldname" disabled />
        </div>
        <div class="flex items-center gap-2">
          <Checkbox :checked="!!field.collapsible" @update:checked="updateField('collapsible', $event)" />
          <Label class="text-sm">Collapsible</Label>
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Depends On</Label>
          <Input :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
        </div>
      </div>
    </template>

    <!-- Regular field selected -->
    <template v-else-if="field && !isLayoutField">
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">{{ field.fieldtype }}</p>

      <!-- Core -->
      <div class="flex flex-col gap-3 mb-5">
        <div class="space-y-1.5">
          <Label class="text-sm">Label *</Label>
          <Input :model-value="field.label" @update:model-value="updateField('label', $event)" />
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Fieldname *</Label>
          <Input :model-value="field.fieldname" @update:model-value="updateField('fieldname', $event)" />
        </div>
        <div class="flex items-center gap-2">
          <Checkbox :checked="!!field.required" @update:checked="updateField('required', $event)" />
          <Label class="text-sm">Required</Label>
        </div>
        <div class="flex items-center gap-2">
          <Checkbox :checked="!!field.hidden" @update:checked="updateField('hidden', $event)" />
          <Label class="text-sm">Hidden</Label>
        </div>
        <div class="flex items-center gap-2">
          <Checkbox :checked="!!field.read_only" @update:checked="updateField('read_only', $event)" />
          <Label class="text-sm">Read Only</Label>
        </div>
      </div>

      <Separator class="mb-4" />

      <!-- Display -->
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Display</p>
      <div class="flex flex-col gap-3 mb-5">
        <div class="flex items-center gap-2">
          <Checkbox :checked="!!field.in_list_view" @update:checked="updateField('in_list_view', $event)" />
          <Label class="text-sm">In List View</Label>
        </div>
        <div class="flex items-center gap-2">
          <Checkbox :checked="!!field.in_filter" @update:checked="updateField('in_filter', $event)" />
          <Label class="text-sm">In Filter</Label>
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Description</Label>
          <Input :model-value="field.description ?? ''" @update:model-value="updateField('description', $event || undefined)" />
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Placeholder</Label>
          <Input :model-value="field.placeholder ?? ''" @update:model-value="updateField('placeholder', $event || undefined)" />
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Depends On</Label>
          <Input :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
        </div>
      </div>

      <!-- Type-specific -->
      <template v-if="field.fieldtype === 'Select'">
        <Separator class="mb-4" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Options</p>
        <textarea
          :value="field.options ?? ''"
          rows="5"
          placeholder="Each option on a new line"
          class="w-full text-sm border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
          @input="updateField('options', ($event.target as HTMLTextAreaElement).value)"
        />
      </template>

      <template v-if="field.fieldtype === 'Link'">
        <Separator class="mb-4" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Linked DocType *</p>
        <Select :model-value="field.options ?? ''" @update:model-value="updateField('options', $event)">
          <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in doctypeOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </template>

      <template v-if="field.fieldtype === 'Table'">
        <Separator class="mb-4" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Child DocType *</p>
        <Select :model-value="field.options ?? ''" @update:model-value="updateField('options', $event)">
          <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in childDoctypeOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </template>

      <template v-if="['Int', 'Float'].includes(field.fieldtype)">
        <Separator class="mb-4" />
        <div class="flex gap-2">
          <div class="flex-1 space-y-1.5">
            <Label class="text-sm">Min</Label>
            <Input :model-value="String(field.min_value ?? '')" type="number" @update:model-value="updateField('min_value', $event ? Number($event) : undefined)" />
          </div>
          <div class="flex-1 space-y-1.5">
            <Label class="text-sm">Max</Label>
            <Input :model-value="String(field.max_value ?? '')" type="number" @update:model-value="updateField('max_value', $event ? Number($event) : undefined)" />
          </div>
        </div>
      </template>
    </template>

    <!-- No selection -->
    <div v-else class="flex items-center justify-center h-32 text-muted-foreground text-sm">
      Оберіть поле для редагування
    </div>
  </div>
</template>
