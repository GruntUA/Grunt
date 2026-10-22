<script setup lang="ts">
import type { BaseFieldProps } from '@/types'

// The value is server-built markup, sanitized on every write
// (HTMLView.parse -> grunt.utils.sanitize), so it is rendered as is.
// Display only: there is nothing to edit, the field never emits.
defineProps<BaseFieldProps>()
</script>

<template>
  <div
    v-if="modelValue"
    class="overflow-x-auto leading-relaxed [&_a]:text-primary [&_a]:underline-offset-4 [&_a:hover]:underline [&_h3]:font-semibold [&_h4]:font-semibold [&_ol]:list-decimal [&_ol]:pl-5 [&_p+p]:mt-2 [&_ul]:list-disc [&_ul]:pl-5 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm [&_td]:border-b [&_td]:px-3 [&_td]:py-2 [&_td]:align-top [&_th]:border-b [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-medium [&_th]:text-muted-foreground [&_thead_th]:bg-muted/50 [&_tr:last-child>td]:border-b-0"
    v-html="String(modelValue)"
  />
  <div v-else class="text-sm text-muted-foreground">—</div>
</template>
