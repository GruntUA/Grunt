<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRichEditorContext } from '../editor/useRichEditor'

// Popup of the "/" menu (extensions/slash.ts drives its state). Fixed to the
// caret; opens upwards when there's no room below.
const { t } = useI18n()
const { slash } = useRichEditorContext()

const list = ref<HTMLElement | null>(null)
const MAX_HEIGHT = 320

const style = computed(() => {
  const r = slash.rect?.()
  if (!r) return { display: 'none' }
  const below = window.innerHeight - r.bottom > MAX_HEIGHT + 8
  return {
    left: `${Math.min(r.left, window.innerWidth - 264)}px`,
    ...(below ? { top: `${r.bottom + 4}px` } : { bottom: `${window.innerHeight - r.top + 4}px` }),
  }
})

// Keep the keyboard-selected item in view.
watch(() => slash.index, () => nextTick(() => {
  list.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' })
}))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="slash.choose" ref="list" role="listbox" :aria-label="t('Insert block')" :style
      class="fixed z-50 max-h-80 w-64 overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
    >
      <button
        v-for="(item, i) in slash.items" :key="item.id" type="button" role="option" :aria-selected="i === slash.index"
        class="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm"
        :class="i === slash.index ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/60'"
        @mousedown.prevent="slash.choose?.(item)" @mouseenter="slash.index = i"
      >
        <component :is="item.icon" class="size-4 text-muted-foreground" />
        {{ item.label }}
      </button>
      <p v-if="!slash.items.length" class="px-2 py-1.5 text-muted-foreground">{{ t('Nothing found') }}</p>
    </div>
  </Teleport>
</template>
