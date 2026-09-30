<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import type { Component } from 'vue'
import { loadLucideLib } from '@/lib/lucide'

/**
 * Renders an icon from:
 *  - a Vue Component           → renders it directly
 *  - a kebab-case Lucide name  → "file-text"  → resolves to <FileText />
 *  - an emoji / other string   → "📁"         → renders as <span>
 */
const props = withDefaults(defineProps<{
  icon: string | Component | undefined
  class?: string
  /** Render unresolvable strings as literal text (e.g. emoji). Set false to silently render nothing instead — for spots where a broken/legacy icon value shouldn't show up as clutter. */
  textFallback?: boolean
}>(), {
  textFallback: true,
})

type IconMap = Record<string, Component>
const lucide = shallowRef<IconMap>({})
let lucideLoaded = false

function ensureLucide() {
  if (lucideLoaded) return
  lucideLoaded = true
  loadLucideLib().then(m => { lucide.value = m })
}

const KEBAB_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/
// Matches genuine emoji/pictographs ("📌", "🏠") — not legacy icon identifiers
// ("octicon octicon-shield-lock") that fail to resolve and shouldn't render as clutter.
const EMOJI_RE = /\p{Extended_Pictographic}/u

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
  if (resolved.value || !props.textFallback) return null
  if (typeof props.icon !== 'string') return null
  return EMOJI_RE.test(props.icon) ? props.icon : null
})
</script>

<template>
  <component :is="resolved" v-if="resolved" :class="props.class" />
  <span v-else-if="textIcon" :class="props.class">{{ textIcon }}</span>
</template>
