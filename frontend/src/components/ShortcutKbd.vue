<script setup lang="ts">
/** A shortcut as shadcn key caps for this platform: `Mod+S` → ⌘ S on macOS, Ctrl S elsewhere. */
import { computed } from 'vue'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { shortcutKeys } from '@/core/shortcuts'

const props = defineProps<{ shortcut: string }>()

const keys = computed(() => shortcutKeys(props.shortcut))
</script>

<template>
  <KbdGroup>
    <Kbd v-for="key in keys" :key="key">{{ key }}</Kbd>
  </KbdGroup>
</template>
