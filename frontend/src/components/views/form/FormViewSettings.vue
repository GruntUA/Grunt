<script setup lang="ts">
import { computed } from 'vue'
import { FileText } from '@lucide/vue'
import { useBuilderStore } from '@/stores/builder'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

const builder = useBuilderStore()

const formView = computed(
  () => builder.doctype?.form_view ?? { layout: 'standard' as const, print_format: null, show_sidebar: true },
)

function updateFormView(patch: Record<string, unknown>) {
  builder.updateDocType({ form_view: { ...formView.value, ...patch } })
}
</script>

<template>
  <div class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center gap-2.5 px-4 py-3 bg-muted/40 border-b border-border">
      <FileText class="size-4 text-muted-foreground" />
      <h3 class="font-semibold text-foreground">Відображення: Форма</h3>
    </div>
    <div class="p-4">
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Розкладка</label>
          <Select :model-value="formView.layout" @update:model-value="updateFormView({ layout: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [
              { value: 'standard', label: 'Стандартна' },
              { value: 'compact', label: 'Компактна' },
              { value: 'wide', label: 'Широка' },
            ]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Формат друку</label>
          <Input
            :model-value="formView.print_format ?? ''"
            placeholder="Назва шаблону"
            class="h-8 text-xs w-full"
            @update:model-value="updateFormView({ print_format: $event || null })"
          />
        </div>
      </div>

      <div class="flex items-center justify-between gap-3 mt-3 pt-3 border-t border-border">
        <div class="flex flex-col">
          <span class="text-xs font-medium text-foreground">Бічна панель</span>
          <span class="text-xs text-muted-foreground">Деталі, теги, зв'язки збоку від форми</span>
        </div>
        <Switch
          :model-value="formView.show_sidebar !== false"
          @update:model-value="updateFormView({ show_sidebar: $event })"
        />
      </div>
    </div>
  </div>
</template>
