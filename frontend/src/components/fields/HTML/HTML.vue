<script setup lang="ts">
import type { BaseFieldProps } from '@/types'

// Content comes from DocType metadata (`options`), which only a System Manager
// can edit — the same people who can already ship client/server scripts — so
// it is rendered as-is, like Frappe's HTML field.
defineProps<BaseFieldProps>()
</script>

<template>
  <div
    class="leading-relaxed [&_a]:text-primary [&_a]:underline-offset-4 hover:[&_a]:underline [&_h3]:font-semibold [&_h4]:font-semibold [&_ol]:list-decimal [&_ol]:pl-5 [&_p+p]:mt-2 [&_ul]:list-disc [&_ul]:pl-5"
    v-html="field.options ?? ''"
  />
</template>
