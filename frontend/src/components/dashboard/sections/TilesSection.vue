<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField, ShortcutItem } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { Plus, Trash2 } from '@lucide/vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import DocTypeCombobox from '@/components/DocTypeCombobox.vue'
import IconPicker from '@/components/fields/Icon/Icon.vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { WIDGET_COLORS, WIDGET_COLOR_LABEL_KEYS } from './widgetHelpers'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

const doctypeNames = computed(() => dtStore.doctypes.filter(d => !d.is_child).map(d => d.name))
const iconField: DocField = { fieldname: 'icon', label: t('Icon (lucide)'), fieldtype: 'Icon' }

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
  <Separator class="!mb-3" />
  <div class="flex items-center justify-between mb-3">
    <p class="font-semibold text-muted-foreground uppercase tracking-wide">{{ t('Tiles') }}</p>
    <Button variant="ghost" size="sm" @click="addTile">
      <Plus class="size-3" /> {{ t('Add') }}
    </Button>
  </div>
  <div class="mb-4 flex flex-col gap-2">
    <div v-if="tiles.length === 0" class="py-3 text-center text-muted-foreground border rounded-md">
      {{ t('No tiles — click «Add»') }}
    </div>
    <div
      v-for="(tile, i) in tiles"
      :key="i"
      class="rounded-md border bg-muted/30 p-3 flex flex-col gap-2"
    >
      <div class="flex items-center justify-between">
        <span class="font-medium text-muted-foreground">{{ t('Tile {n}', { n: i + 1 }) }}</span>
        <Button variant="ghost" size="icon-sm" class="text-muted-foreground hover:text-destructive" @click="removeTile(i)">
          <Trash2 class="size-3.5" />
        </Button>
      </div>
      <Input
        :model-value="tile.title"
        :placeholder="t('Title')"
        class="w-full"
        @update:model-value="updateTile(i, 'title', String($event))"
      />
      <div class="flex items-center gap-2">
        <IconPicker
          :field="iconField"
          :model-value="tile.icon ?? null"
          @update:model-value="updateTile(i, 'icon', String($event ?? ''))"
        />
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          class="flex-1 flex-wrap"
          :model-value="tile.link_type"
          @update:model-value="(v) => v && updateTile(i, 'link_type', String(v))"
        >
          <ToggleGroupItem value="DocType" class="flex-1">DocType</ToggleGroupItem>
          <ToggleGroupItem value="Report" class="flex-1">{{ t('Report') }}</ToggleGroupItem>
          <ToggleGroupItem value="Page" class="flex-1">Page</ToggleGroupItem>
          <ToggleGroupItem value="URL" class="flex-1">URL</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <DocTypeCombobox
        v-if="tile.link_type === 'DocType'"
        :model-value="tile.link_to"
        :options="doctypeNames"
        class="w-full"
        @update:model-value="updateTile(i, 'link_to', $event)"
      />
      <Input
        v-else
        :model-value="tile.link_to"
        :placeholder="t('URL or name...')"
        class="w-full"
        @update:model-value="updateTile(i, 'link_to', String($event))"
      />
      <ToggleGroup
        type="single"
        variant="outline"
        class="w-fit"
        :model-value="tile.color ?? 'primary'"
        @update:model-value="(v) => v && updateTile(i, 'color', String(v))"
      >
        <ToggleGroupItem
          v-for="c in WIDGET_COLORS" :key="c.value" :value="c.value"
          :title="t(WIDGET_COLOR_LABEL_KEYS[c.value])"
          :aria-label="t(WIDGET_COLOR_LABEL_KEYS[c.value])"
          class="p-1"
        >
          <span class="size-3 rounded-full" :style="{ background: c.bg }" />
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
  </div>
</template>
