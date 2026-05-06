<script setup lang="ts">
import { computed } from 'vue'
import { FileText } from '@lucide/vue'
import { useBuilderStore } from '@/stores/builder'

const builder = useBuilderStore()

const formView = computed(
  () => builder.doctype?.form_view ?? { layout: 'standard' as const, print_format: null },
)

function updateFormView(patch: Record<string, unknown>) {
  builder.updateDocType({ form_view: { ...formView.value, ...patch } })
}
</script>

<template>
  <div class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center gap-2.5 px-4 py-3 bg-muted/40 border-b border-border">
      <FileText class="size-4 text-muted-foreground" />
      <h3 class="text-sm font-semibold text-foreground">Відображення: Форма</h3>
    </div>
    <div class="p-4">
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Розкладка</label>
          <Select
            :model-value="formView.layout"
            :options="[
              { value: 'standard', label: 'Стандартна' },
              { value: 'compact', label: 'Компактна' },
              { value: 'wide', label: 'Широка' },
            ]"
            option-label="label"
            option-value="value"
            class="h-8 text-xs"
            @update:model-value="updateFormView({ layout: $event })"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Формат друку</label>
          <InputText
            :model-value="formView.print_format ?? ''"
            placeholder="Назва шаблону"
            class="h-8 text-xs w-full"
            @update:model-value="updateFormView({ print_format: $event || null })"
          />
        </div>
      </div>
    </div>
  </div>
</template>
