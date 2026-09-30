<script setup lang="ts">
/** A Lucide icon by kebab-case name (`trash-2`), loaded lazily. */
import { computed, shallowRef, type Component } from 'vue'
import { loadLucideLib } from '@/lib/lucide'

const props = defineProps<{ name?: string | null }>()

const icons = shallowRef<Record<string, Component> | null>(null)
let loading: Promise<void> | null = null

const component = computed(() => {
  const raw = String(props.name ?? '').trim()
  if (!raw) return null
  if (!icons.value) {
    loading ??= loadLucideLib().then((lib) => {
      icons.value = lib
    })
    return null
  }
  const pascal = raw.split('-').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return icons.value[pascal] ?? null
})
</script>

<template>
  <component :is="component" v-if="component" />
</template>
