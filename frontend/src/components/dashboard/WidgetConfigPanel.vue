<script setup lang="ts">
import { computed, defineAsyncComponent, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { getWidgetDef, getPaletteGroups } from '@/core/widgetRegistry'
import { getWidgetSection } from '@/core/widgetSectionRegistry'
import { WIDGET_FIELD_KEY, WIDGET_UPDATE_KEY } from '@/core/composables/useWidgetPropertyEditor'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import AppIcon from '@/components/AppIcon.vue'
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

const typeGroups = getPaletteGroups()
const def = computed(() => draft.value ? getWidgetDef(draft.value.widget_type) : undefined)
const configSections = computed(() => def.value?.configSections ?? [])

const sectionComponents = computed(() =>
  configSections.value.map(name => {
    const sectionDef = getWidgetSection(name)
    return sectionDef ? defineAsyncComponent(sectionDef.component) : null
  })
)

function changeType(next: unknown) {
  if (!draft.value || !next || next === draft.value.widget_type) return
  updateWidget('widget_type', String(next))
}
</script>

<template>
  <div v-if="!draft" class="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-6">
    <div class="text-4xl">👈</div>
    <p class="text-center">{{ t('Select a widget on the canvas or add a new one from the palette') }}</p>
  </div>

  <div v-else class="flex flex-col h-full overflow-hidden">
    <div class="px-4 py-3 border-b shrink-0 flex items-center justify-between">
      <span class="font-semibold uppercase tracking-wide text-muted-foreground">{{ def ? t(def.label) : t('Settings') }}</span>
      <Button variant="ghost" size="sm" class="text-destructive hover:text-destructive" @click="emit('remove')">
        <Trash2 class="size-3" /> {{ t('Delete') }}
      </Button>
    </div>

    <div class="flex-1 overflow-y-auto p-4">

      <!-- Widget type -->
      <div class="flex flex-col gap-1.5 mb-4">
        <label class="font-medium">{{ t('Type') }}</label>
        <Select :model-value="draft.widget_type" @update:model-value="changeType">
          <SelectTrigger class="w-full">
            <SelectValue>
              <span class="flex items-center gap-2">
                <AppIcon v-if="def" :icon="def.icon" class="size-4 shrink-0 text-muted-foreground" />
                {{ def ? t(def.label) : draft.widget_type }}
              </span>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup v-for="group in typeGroups" :key="group.category">
              <SelectLabel>{{ group.category }}</SelectLabel>
              <SelectItem v-for="wt in group.widgets" :key="wt.type" :value="wt.type">
                <span class="flex items-center gap-2">
                  <AppIcon :icon="wt.icon" class="size-4 shrink-0 text-muted-foreground" />
                  {{ t(wt.label) }}
                </span>
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
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
