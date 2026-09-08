<script setup lang="ts">
import { computed, provide, watch, defineAsyncComponent } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { getFieldDef, getPaletteGroups, getLayoutTypeSet } from '@/core/fieldRegistry'
import { getPropertySection } from '@/core/propertySectionRegistry'
import { describeTypeChange, type TypeChangeNote } from '@/core/fieldStorage'
import { PROPERTY_FIELD_KEY, PROPERTY_UPDATE_KEY } from '@/core/composables/usePropertyEditor'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'

// Register all core sections (side-effect import)
import '@/pages/studio/builder/sections/index'

const builder = useBuilderStore()
const field = computed(() => builder.selectedField)
const config = computed(() => field.value ? getFieldDef(field.value.fieldtype) : undefined)
const sections = computed(() => config.value?.propertySections ?? [])

function updateField(key: string, val: unknown) {
  if (builder.selectedFieldName === null) return
  builder.updateField(builder.selectedFieldName, { [key]: val } as never)
}

provide(PROPERTY_FIELD_KEY, field as never)
provide(PROPERTY_UPDATE_KEY, updateField)

const sectionComponents = computed(() =>
  sections.value.map(name => {
    const def = getPropertySection(name)
    return def ? defineAsyncComponent(def.component) : null
  })
)

// ── Field-type switcher ──────────────────────────────────────────────────────
// Layout separators (Section / Column / Tab) are structural — their type is
// managed by the canvas, not here — so the switcher is hidden for them.
const LAYOUT_TYPES = getLayoutTypeSet()
const isLayoutField = computed(() => !!field.value && LAYOUT_TYPES.has(field.value.fieldtype))
const typeGroups = getPaletteGroups()

// Remember each field's type as first seen this session, so the compatibility
// note reflects the pending change and clears itself if the user reverts.
const seenType = new Map<string, string>()
watch(field, (f) => {
  if (f && !seenType.has(f.fieldname)) seenType.set(f.fieldname, f.fieldtype)
}, { immediate: true })

const typeNote = computed<TypeChangeNote | null>(() => {
  const f = field.value
  if (!f) return null
  const from = seenType.get(f.fieldname)
  return from ? describeTypeChange(from, f.fieldtype) : null
})

function changeType(next: unknown) {
  if (!next || next === field.value?.fieldtype) return
  updateField('fieldtype', String(next))
}
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-border bg-card">
    <template v-if="field && config">
      <!-- Header -->
      <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-4">
        {{ config.label }}
      </p>

      <!-- Field type -->
      <div v-if="!isLayoutField" class="flex flex-col gap-1.5 mb-4">
        <label class="font-medium">Тип поля</label>
        <Select :model-value="field.fieldtype" @update:model-value="changeType">
          <SelectTrigger class="w-full">
            <SelectValue :placeholder="field.fieldtype" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup v-for="group in typeGroups" :key="group.category">
              <SelectLabel>{{ group.category || 'Інше' }}</SelectLabel>
              <SelectItem v-for="def in group.fields" :key="def.type" :value="def.type">
                {{ def.label }}
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <p
          v-if="typeNote"
          class="rounded-md border px-2 py-1.5"
          :class="typeNote.severity === 'danger'
            ? 'border-destructive/30 bg-destructive/5 text-destructive'
            : 'border-amber-400/40 bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'"
        >
          {{ typeNote.message }}
        </p>
      </div>

      <!-- Registered sections -->
      <component
        :is="component"
        v-for="(component, i) in sectionComponents"
        :key="sections[i]"
      />
    </template>

    <!-- No selection -->
    <div v-else class="flex items-center justify-center h-32 text-muted-foreground">
      Оберіть поле для редагування
    </div>
  </div>
</template>
