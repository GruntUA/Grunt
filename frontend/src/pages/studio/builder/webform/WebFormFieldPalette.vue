<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { useBuilderStore } from '@/stores/builder'
import type { DocField } from '@/types'

const { t } = useI18n()

const props = defineProps<{
  targetFields: DocField[]
}>()

const builder = useBuilderStore()

// Tab/Section/Column are the *target* DocType's own layout scaffolding, not
// data fields — dragging one in would just add a meaningless empty marker.
// Table needs UI a plain <form> can't provide; JSON/Code are raw data fields.
const EXCLUDED_TYPES = new Set(['Tab', 'Section', 'Column', 'Table', 'JSON', 'Code'])

const addedNames = computed(
  () => new Set((builder.doctype?.fields ?? []).map((f) => f.fieldname)),
)

const available = computed(() =>
  props.targetFields.filter(
    (f) => !addedNames.value.has(f.fieldname) && !EXCLUDED_TYPES.has(f.fieldtype),
  ),
)

// The target DocType's own `hidden` describes its normal desk form, not this
// webform — a field an admin explicitly drags in here should start visible.
function cloneField(item: DocField): DocField {
  return { ...item, hidden: false }
}

function addSection() {
  builder.addField('Section')
}
</script>

<template>
  <div class="h-full overflow-y-auto p-3 border-r border-border bg-background">
    <p class="font-semibold text-muted-foreground/70 uppercase tracking-wide mb-3 px-1">
      {{ t('DocType fields') }}
    </p>

    <VueDraggable
      :model-value="available"
      :group="{ name: 'builder-fields', pull: 'clone', put: false }"
      :sort="false"
      :clone="cloneField"
      class="flex flex-col gap-0.5 mb-1"
    >
      <div
        v-for="item in available"
        :key="item.fieldname"
        class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-border transition-colors text-left w-full cursor-grab active:cursor-grabbing"
      >
        <span class="text-foreground">{{ item.label || item.fieldname }}</span>
      </div>
    </VueDraggable>
    <p v-if="!available.length" class="text-muted-foreground/60 px-2 mb-4">
      {{ t('All eligible fields are already added') }}
    </p>

    <div class="mb-4 mt-3">
      <p class="text-muted-foreground/70 px-1 mb-1">{{ t('Structural') }}</p>
      <button
        type="button"
        class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-border transition-colors text-left w-full"
        @click="addSection"
      >
        <span class="text-foreground">{{ t('Section') }}</span>
      </button>
    </div>
  </div>
</template>
