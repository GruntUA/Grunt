<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Dashboard (Connections)</p>
  
  <div class="flex flex-col gap-4 mb-4">
    <!-- Show in Dashboard -->
    <div class="flex items-center gap-2">
      <Checkbox
        :model-value="field.show_in_dashboard"
        @update:model-value="updateField('show_in_dashboard', $event)"
      />
      <label class="font-medium cursor-pointer" @click="updateField('show_in_dashboard', !field.show_in_dashboard)">
        Показувати в дашборді
      </label>
    </div>

    <!-- Dashboard DocType -->
    <div v-if="field.show_in_dashboard" class="flex flex-col gap-1.5">
      <label class="font-medium">DocType для значка</label>
      <Input
        :model-value="field.dashboard_doctype ?? ''"
        placeholder="напр. Employee"
        class="w-full"
        @update:model-value="updateField('dashboard_doctype', $event || undefined)"
      />
    </div>

    <!-- Dashboard Link Field -->
    <div v-if="field.show_in_dashboard" class="flex flex-col gap-1.5">
      <label class="font-medium">Поле зв'язку (Back-link)</label>
      <Input
        :model-value="field.dashboard_link_field ?? ''"
        placeholder="напр. department"
        class="w-full"
        @update:model-value="updateField('dashboard_link_field', $event || undefined)"
      />
      <p class="text-xs text-muted-foreground leading-relaxed mt-1">
        Назва поля у цільовому DocType, яке посилається на цей документ. 
        Використовується для фільтрації списку та автозаповнення при створенні.
      </p>
    </div>
  </div>
</template>
