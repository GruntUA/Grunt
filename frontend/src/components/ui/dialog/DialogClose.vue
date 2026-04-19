<script setup lang="ts">
import { inject } from 'vue'

const ctx = inject<any>('$dialog')
</script>

<template>
  <span data-slot="dialog-close" @click="ctx?.close()">
    <slot />
  </span>
</template>
