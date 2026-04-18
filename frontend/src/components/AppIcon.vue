<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import type { Component } from 'vue'

/**
 * Renders an icon from:
 *  - a Vue Component           → renders it directly
 *  - a kebab-case Lucide name  → "file-text"  → resolves to <FileText />
 *  - an emoji / other string   → "📁"         → renders as <span>
 */
const props = defineProps<{
  icon: string | Component | undefined
  class?: string
}>()

type IconMap = Record<string, Component>
const lucide = shallowRef<IconMap>({})
let lucideLoaded = false

function ensureLucide() {
  if (lucideLoaded) return
  lucideLoaded = true
  import('@lucide/vue').then(m => { lucide.value = m as unknown as IconMap })
}

const KEBAB_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/

const resolved = computed<Component | null>(() => {
  const ic = props.icon
  if (!ic) return null
  if (typeof ic !== 'string') return ic as Component
  if (!KEBAB_RE.test(ic)) return null                           // emoji or arbitrary string
  ensureLucide()
  const pascal = ic.split('-').map(s => s[0].toUpperCase() + s.slice(1)).join('')
  return (lucide.value[pascal] as Component) ?? null
})

const textIcon = computed<string | null>(() => {
  if (resolved.value) return null
  return typeof props.icon === 'string' ? props.icon : null
})
</script>

<template>
  <component :is="resolved" v-if="resolved" :class="props.class" />
  <span v-else-if="textIcon" :class="props.class">{{ textIcon }}</span>
</template>
