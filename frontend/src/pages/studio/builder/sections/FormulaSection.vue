<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <div class="flex items-center justify-between mb-3">
    <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Formula</p>
    <span
      v-if="field.formula"
      class="text-xs font-mono text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 px-1.5 py-0.5 rounded"
    >ƒx активна</span>
  </div>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex flex-col gap-1.5">
      <label class="font-medium">Вираз (Python)</label>
      <Textarea
        :model-value="field.formula ?? ''"
        rows="2"
        placeholder="qty * unit_price"
        class="w-full !text-sm !font-mono"
        @update:model-value="(v: string | number) => updateField('formula', String(v).trim() || null)"
      />
      <p class="text-xs text-muted-foreground leading-relaxed">
        Обчислюється при кожному збереженні. Доступні всі поля документа як змінні.<br>
        Приклади: <code class="bg-muted px-1 rounded">qty * price</code>,
        <code class="bg-muted px-1 rounded">round(a + b, 2)</code>,
        <code class="bg-muted px-1 rounded">first_name + ' ' + last_name</code>
      </p>
    </div>
    <div v-if="field.formula" class="flex items-center gap-2 pt-1 pl-0.5">
      <Checkbox :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
      <label class="text-muted-foreground cursor-pointer font-medium">Read Only (рекомендовано)</label>
    </div>
  </div>
</template>
