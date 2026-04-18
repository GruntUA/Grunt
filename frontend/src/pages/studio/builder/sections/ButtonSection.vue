<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Separator } from '@/components/ui/separator'
import { Label } from '@/components/ui/label'
import IconPicker from '@/components/fields/Icon/Icon.vue'

const { field, updateField } = usePropertyEditor()

const VARIANTS = [
  { value: 'default',     label: 'Primary' },
  { value: 'secondary',   label: 'Secondary' },
  { value: 'destructive', label: 'Destructive' },
  { value: 'outline',     label: 'Outline' },
  { value: 'ghost',       label: 'Ghost' },
]

const current = () => field.value.options ?? 'default'
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Button</p>

  <!-- Style -->
  <div class="mb-4">
    <Label class="text-xs text-muted-foreground mb-2 block">Style</Label>
    <div class="flex flex-wrap gap-1.5">
      <button
        v-for="v in VARIANTS"
        :key="v.value"
        type="button"
        class="px-2.5 py-1 text-xs rounded border transition-colors"
        :class="current() === v.value
          ? 'bg-primary text-primary-foreground border-primary'
          : 'bg-background text-muted-foreground border-border hover:border-primary/50 hover:text-foreground'"
        @click="updateField('options', v.value)"
      >
        {{ v.label }}
      </button>
    </div>
  </div>

  <!-- Icon -->
  <div class="mb-4">
    <Label class="text-xs text-muted-foreground mb-2 block">Icon</Label>
    <IconPicker
      :field="field"
      :model-value="field.icon ?? null"
      @update:model-value="updateField('icon', $event ?? undefined)"
    />
  </div>
</template>
