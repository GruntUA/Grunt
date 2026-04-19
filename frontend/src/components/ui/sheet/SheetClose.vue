<script setup lang="ts">
import { inject } from 'vue'

const ctx = inject<any>('$sheet')
</script>

<template>
  <span data-slot="sheet-close" @click="ctx?.close()">
    <slot />
  </span>
</template>
