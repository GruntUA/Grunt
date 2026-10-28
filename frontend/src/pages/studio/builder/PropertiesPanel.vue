<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, provide, ref, watch, defineAsyncComponent } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { appsApi, type GruntApp } from '@/core/api'
import { getFieldDef, getPaletteGroups, getLayoutTypeSet } from '@/core/fieldRegistry'
import { getPropertySection } from '@/core/propertySectionRegistry'
import { describeTypeChange, type TypeChangeNote } from '@/core/fieldStorage'
import { PROPERTY_FIELD_KEY, PROPERTY_UPDATE_KEY } from '@/core/composables/usePropertyEditor'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'

// Register all core sections (side-effect import)
import '@/pages/studio/builder/sections/index'

const { t } = useI18n()

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

// Field-type switcher
// Layout separators (Section / Column / Tab) are structural - their type is
// managed by the canvas, not here - so the switcher is hidden for them.
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

// Which app the field belongs to ("Customize"): another app's field is saved
// into that app's doctype_ext/<DocType>.json, not into this DocType's JSON.
const OWN = '__own__'
const apps = ref<GruntApp[]>([])
onMounted(async () => {
  try {
    apps.value = await appsApi.list()
  } catch {
    apps.value = []
  }
})
const ownApp = computed(() => builder.doctype?.app || '')
const otherApps = computed(() => apps.value.filter(a => a.name !== ownApp.value && a.name !== 'grunt'))
const fieldApp = computed(() => {
  const app = field.value?.source_app
  return app && app !== ownApp.value ? app : OWN
})
function changeApp(next: unknown) {
  updateField('source_app', next === OWN || !next ? null : String(next))
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
      <Field v-if="!isLayoutField" class="mb-4">
        <FieldLabel for="builder-field-type">{{ t('Field type') }}</FieldLabel>
        <Select :model-value="field.fieldtype" @update:model-value="changeType">
          <SelectTrigger id="builder-field-type" class="w-full">
            <SelectValue :placeholder="field.fieldtype" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup v-for="group in typeGroups" :key="group.category">
              <SelectLabel>{{ group.category ? t(group.category) : t('Other') }}</SelectLabel>
              <SelectItem v-for="def in group.fields" :key="def.type" :value="def.type">
                {{ def.label }}
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Alert v-if="typeNote" :variant="typeNote.severity === 'danger' ? 'destructive' : 'default'">
          <AlertDescription>{{ typeNote.message }}</AlertDescription>
        </Alert>
      </Field>

      <!-- Registered sections -->
      <component
        :is="component"
        v-for="(component, i) in sectionComponents"
        :key="sections[i]"
      />

      <!-- Owner app -->
      <Field v-if="otherApps.length" class="mt-4">
        <FieldLabel for="builder-field-app">{{ t('Belongs to app') }}</FieldLabel>
        <Select :model-value="fieldApp" @update:model-value="changeApp">
          <SelectTrigger id="builder-field-app" class="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem :value="OWN">{{ ownApp ? t('This DocType ({app})', { app: ownApp }) : t('This DocType') }}</SelectItem>
            <SelectItem v-for="app in otherApps" :key="app.name" :value="app.name">
              {{ app.title || app.name }}
            </SelectItem>
          </SelectContent>
        </Select>
        <FieldDescription>
          {{ t("Another app's field is saved into that app's doctype_ext/ file and leaves with it.") }}
        </FieldDescription>
      </Field>
    </template>

    <!-- No selection -->
    <div v-else class="flex items-center justify-center h-32 text-muted-foreground">
      {{ t('Select a field to edit') }}
    </div>
  </div>
</template>
