<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Fetch From</p>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="text-sm font-medium">Отримувати з (Fetch From)</label>
    <InputText
      :model-value="field.fetch_from ?? ''"
      placeholder="напр. link_field.source_field"
      class="w-full"
      @update:model-value="updateField('fetch_from', $event || undefined)"
    />
    <p class="text-[11px] text-muted-foreground leading-relaxed mt-1">
      Автоматично заповнювати значення з іншого документа при виборі зв'язкового поля (Link). 
      Формат: <code class="bg-muted px-1 rounded">назва_лінк_поля.назва_поля_крапки</code>
    </p>
  </div>
</template>
