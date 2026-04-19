<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <div class="flex items-center justify-between mb-3">
    <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Formula</p>
    <span
      v-if="field.formula"
      class="text-[10px] font-mono text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 px-1.5 py-0.5 rounded"
    >ƒx активна</span>
  </div>
  <div class="flex flex-col gap-2 mb-4">
    <div class="space-y-1.5">
      <Label class="text-sm">Вираз (Python)</Label>
      <textarea
        :value="field.formula ?? ''"
        rows="2"
        placeholder="qty * unit_price"
        class="w-full text-sm font-mono border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring resize-none"
        @input="updateField('formula', ($event.target as HTMLTextAreaElement).value.trim() || null)"
      />
      <p class="text-[11px] text-muted-foreground leading-relaxed">
        Обчислюється при кожному збереженні. Доступні всі поля документа як змінні.<br>
        Приклади: <code class="bg-muted px-1 rounded">qty * price</code>,
        <code class="bg-muted px-1 rounded">round(a + b, 2)</code>,
        <code class="bg-muted px-1 rounded">first_name + ' ' + last_name</code>
      </p>
    </div>
    <div v-if="field.formula" class="flex items-center gap-2 pt-1 pl-0.5">
      <Checkbox binary :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
      <Label class="text-sm text-muted-foreground cursor-pointer">Read Only (рекомендовано)</Label>
    </div>
  </div>
</template>
