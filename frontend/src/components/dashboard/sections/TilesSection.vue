<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ShortcutItem } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { Plus, Trash2 } from '@lucide/vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { WIDGET_COLORS, WIDGET_COLOR_LABEL_KEYS } from './widgetHelpers'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

const tiles = computed<ShortcutItem[]>(() => {
  try { return JSON.parse(widget.value.content ?? '[]') } catch { return [] }
})

function setTiles(val: ShortcutItem[]) {
  updateWidget('content', JSON.stringify(val))
}

function addTile() {
  setTiles([...tiles.value, { title: t('New'), icon: 'Link', link_type: 'DocType', link_to: '', color: 'primary' }])
}

function removeTile(i: number) {
  const arr = [...tiles.value]
  arr.splice(i, 1)
  setTiles(arr)
}

function updateTile(i: number, key: keyof ShortcutItem, value: string) {
  setTiles(tiles.value.map((t, idx) => idx === i ? { ...t, [key]: value } : t))
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Tiles') }}</label>
      <button class="flex items-center gap-1 text-primary hover:underline" @click="addTile">
        <Plus class="size-3" /> {{ t('Add') }}
      </button>
    </div>
    <div v-if="tiles.length === 0" class="py-3 text-center text-muted-foreground border rounded-md">
      {{ t('No tiles — click «Add»') }}
    </div>
    <div
      v-for="(tile, i) in tiles"
      :key="i"
      class="rounded-md border bg-muted/30 p-3 space-y-2"
    >
      <div class="flex items-center justify-between">
        <span class="font-medium text-muted-foreground">{{ t('Tile {n}', { n: i + 1 }) }}</span>
        <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeTile(i)">
          <Trash2 class="size-3.5" />
        </button>
      </div>
      <input
        :value="tile.title"
        class="w-full h-7 px-2.5 rounded border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        :placeholder="t('Title')"
        @input="updateTile(i, 'title', ($event.target as HTMLInputElement).value)"
      />
      <div class="grid grid-cols-2 gap-1.5">
        <input
          :value="tile.icon"
          class="h-7 px-2.5 rounded border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          :placeholder="t('Icon (lucide)')"
          @input="updateTile(i, 'icon', ($event.target as HTMLInputElement).value)"
        />
        <select
          :value="tile.link_type"
          class="h-7 px-2 rounded border bg-background focus:outline-none"
          @change="updateTile(i, 'link_type', ($event.target as HTMLSelectElement).value)"
        >
          <option value="DocType">DocType</option>
          <option value="Report">{{ t('Report') }}</option>
          <option value="Page">Page</option>
          <option value="URL">URL</option>
        </select>
      </div>
      <select
        v-if="tile.link_type === 'DocType'"
        :value="tile.link_to"
        class="w-full h-7 px-2 rounded border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        @change="updateTile(i, 'link_to', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">{{ t('— Select —') }}</option>
        <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">{{ dt.label }}</option>
      </select>
      <input
        v-else
        :value="tile.link_to"
        class="w-full h-7 px-2.5 rounded border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        :placeholder="t('URL or name...')"
        @input="updateTile(i, 'link_to', ($event.target as HTMLInputElement).value)"
      />
      <!-- Tile color -->
      <div class="flex gap-1.5">
        <button
          v-for="c in WIDGET_COLORS" :key="c.value"
          :title="t(WIDGET_COLOR_LABEL_KEYS[c.value])"
          :class="['w-5 h-5 rounded-full border-2 transition-colors', tile.color === c.value ? 'border-foreground scale-110' : 'border-transparent']"
          :style="{ background: c.bg }"
          @click="updateTile(i, 'color', c.value)"
        />
      </div>
    </div>
  </div>
</template>
