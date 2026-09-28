<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Fetch From</p>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Fetch From') }}</label>
    <Input
      :model-value="field.fetch_from ?? ''"
      :placeholder="t('e.g. link_field.source_field')"
      class="w-full"
      @update:model-value="updateField('fetch_from', $event || undefined)"
    />
    <p class="text-muted-foreground leading-relaxed mt-1">
      {{ t('Fill the value automatically from another document when a Link field is chosen.') }}
      {{ t('Format:') }} <code class="bg-muted px-1 rounded">link_field.source_field</code>
    </p>
  </div>
</template>
