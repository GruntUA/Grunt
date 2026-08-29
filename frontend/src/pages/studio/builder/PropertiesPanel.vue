<script setup lang="ts">
import { computed, provide, defineAsyncComponent } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { getFieldDef } from '@/core/fieldRegistry'
import { getPropertySection } from '@/core/propertySectionRegistry'
import { PROPERTY_FIELD_KEY, PROPERTY_UPDATE_KEY } from '@/core/composables/usePropertyEditor'
import { TriangleAlert } from '@lucide/vue'

// Register all core sections (side-effect import)
import '@/pages/studio/builder/sections/index'

const builder = useBuilderStore()
const field = computed(() => builder.selectedField)
const config = computed(() => field.value ? getFieldDef(field.value.fieldtype) : undefined)
const sections = computed(() => config.value?.propertySections ?? [])

const fieldHint = computed(() =>
  field.value
    ? builder.indexHints.find(h => h.field === field.value!.fieldname) ?? null
    : null
)

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
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-border bg-card">
    <template v-if="field && config">
      <!-- Header -->
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
        {{ config.label }}
      </p>

      <!-- Index hint -->
      <div v-if="fieldHint" class="flex gap-2 rounded-md border border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30 p-3 mb-4 text-xs text-yellow-800 dark:text-yellow-300">
        <TriangleAlert class="size-4 shrink-0 mt-px text-yellow-500" />
        <div class="flex-1">
          <p>{{ fieldHint.reason }}</p>
          <button
            type="button"
            class="mt-1.5 font-semibold underline underline-offset-2 hover:opacity-75"
            @click="updateField('index', true)"
          >Додати index: true</button>
        </div>
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
