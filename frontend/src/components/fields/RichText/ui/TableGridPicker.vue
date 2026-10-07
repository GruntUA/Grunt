<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

// Hover a rows × columns grid, click to insert a table of that size.
const emit = defineEmits<{ pick: [rows: number, cols: number] }>()

const SIZE = 8
const { t } = useI18n()
const hover = ref({ rows: 0, cols: 0 })
</script>

<template>
  <div class="p-1" @mouseleave="hover = { rows: 0, cols: 0 }">
    <div class="grid gap-0.5" :style="{ gridTemplateColumns: `repeat(${SIZE}, 1rem)` }">
      <template v-for="r in SIZE" :key="r">
        <button
          v-for="c in SIZE" :key="c" type="button"
          class="size-4 rounded-[2px] border border-border"
          :class="r <= hover.rows && c <= hover.cols ? 'border-primary bg-primary/20' : 'bg-background'"
          :aria-label="t('{rows} × {cols} table', { rows: r, cols: c })"
          @mouseenter="hover = { rows: r, cols: c }"
          @focus="hover = { rows: r, cols: c }"
          @click="emit('pick', r, c)"
        />
      </template>
    </div>
    <p class="mt-1.5 text-center text-muted-foreground tabular-nums">
      {{ hover.rows ? `${hover.rows} × ${hover.cols}` : t('Table size') }}
    </p>
  </div>
</template>
