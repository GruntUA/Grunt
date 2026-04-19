<script setup lang="ts">
import { inject } from 'vue'

const ctx = inject<any>('$dialog')
</script>

<template>
  <span data-slot="dialog-trigger" @click="ctx?.open()">
    <slot />
  </span>
</template>
