<script setup lang="ts">
import { computed, defineAsyncComponent, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { getWidgetDef, getPaletteWidgets } from '@/core/widgetRegistry'
import { getWidgetSection } from '@/core/widgetSectionRegistry'
import { WIDGET_FIELD_KEY, WIDGET_UPDATE_KEY } from '@/core/composables/useWidgetPropertyEditor'
import { Trash2 } from '@lucide/vue'

// Register all core sections (side-effect import)
import './sections/index'

const props = defineProps<{ widget: DashboardWidget | null }>()
const emit = defineEmits<{
  change: [widget: DashboardWidget]
  remove: []
}>()

const { t } = useI18n()
const dtStore = useDocTypeStore()
dtStore.loadAll()

const draft = ref<DashboardWidget | null>(null)

watch(() => props.widget, (w) => {
  if (!w) {
    draft.value = null
  } else if (draft.value?.id !== w.id) {
    draft.value = { ...w }
  }
}, { immediate: true })

function apply() {
  if (draft.value) emit('change', { ...draft.value })
}

function updateWidget(key: string, val: unknown) {
  if (!draft.value) return
  draft.value = { ...draft.value, [key]: val }
  apply()
}

provide(WIDGET_FIELD_KEY, draft as never)
provide(WIDGET_UPDATE_KEY, updateWidget)

const paletteWidgets = getPaletteWidgets()
const def = computed(() => draft.value ? getWidgetDef(draft.value.widget_type) : undefined)
const configSections = computed(() => def.value?.configSections ?? [])

const sectionComponents = computed(() =>
  configSections.value.map(name => {
    const sectionDef = getWidgetSection(name)
    return sectionDef ? defineAsyncComponent(sectionDef.component) : null
  })
)

function changeType(next: string) {
  if (!draft.value || next === draft.value.widget_type) return
  updateWidget('widget_type', next)
}
</script>

<template>
  <div v-if="!draft" class="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-6">
    <div class="text-4xl">👈</div>
    <p class="text-center">{{ t('Select a widget on the canvas or add a new one from the palette') }}</p>
  </div>

  <div v-else class="flex flex-col h-full overflow-hidden">
    <div class="px-4 py-3 border-b shrink-0 flex items-center justify-between">
      <span class="font-semibold uppercase tracking-wide text-muted-foreground">{{ t('Settings') }}</span>
      <button
        class="text-destructive hover:underline flex items-center gap-1"
        @click="emit('remove')"
      >
        <Trash2 class="size-3" /> {{ t('Delete') }}
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-4">

      <!-- Widget type -->
      <div class="space-y-1.5">
        <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Type') }}</label>
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="wt in paletteWidgets" :key="wt.type"
            :class="[
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border transition-colors',
              draft.widget_type === wt.type
                ? 'bg-primary text-primary-foreground border-primary'
                : 'hover:bg-muted border-border',
            ]"
            @click="changeType(wt.type)"
          >
            <span>{{ wt.icon }}</span>{{ t(wt.label) }}
          </button>
        </div>
      </div>

      <!-- Registered sections -->
      <component
        :is="component"
        v-for="(component, i) in sectionComponents"
        :key="configSections[i]"
      />

    </div>
  </div>
</template>
