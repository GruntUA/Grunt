<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()

function toggle() {
  updateField('show_connections', !field.value.show_connections)
}
</script>

<template>
  <Separator class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Вкладка</p>
  <div class="mb-4">
    <div class="flex items-start gap-2">
      <Checkbox
        :model-value="!!field.show_connections"
        class="mt-0.5 shrink-0"
        @update:model-value="updateField('show_connections', $event)"
      />
      <span
        class="text-sm font-medium text-foreground leading-snug cursor-pointer select-none"
        @click="toggle"
      >
        Показувати панель «Зв'язки» в цій вкладці
      </span>
    </div>
    <p class="mt-1.5 text-xs text-muted-foreground leading-snug">
      Пов'язані документи (лічильники, «+ Новий») рендеряться зверху цієї вкладки.
      Якщо вимкнено скрізь — панель показується над формою.
    </p>
  </div>
</template>
