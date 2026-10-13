<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { TriangleAlert } from '@lucide/vue'
import { useBuilderStore } from '@/stores/builder'
import type { IndexHint } from '@/types'
import { Button } from '@/components/ui/button'

const { t } = useI18n()

const builder = useBuilderStore()

// All current hints are polymorphic-pair suggestions ("a+b") - see
// core/indexHints.ts for why single-field hints were dropped.
function applyHint(hint: IndexHint) {
  const [a, b] = hint.field.split('+')
  builder.updateDocType({ indexes: [...(builder.doctype?.indexes ?? []), [a, b]] })
}
</script>

<template>
  <div v-if="builder.indexHints.length" class="flex flex-col gap-1.5 border-b border-amber-400/40 bg-amber-50 px-4 py-2 text-xs text-amber-700 dark:bg-amber-950/20 dark:text-amber-400">
    <div v-for="hint in builder.indexHints" :key="hint.field" class="flex items-start gap-2">
      <TriangleAlert class="size-4 shrink-0 mt-px" />
      <div class="flex-1">
        <span>{{ hint.reason }}</span>
        <Button type="button" variant="link" size="xs" class="ml-1 h-auto p-0 text-inherit" @click="applyHint(hint)">
          {{ t('Add index') }}
        </Button>
      </div>
    </div>
  </div>
</template>
