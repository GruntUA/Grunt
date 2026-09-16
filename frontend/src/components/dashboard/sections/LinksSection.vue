<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { WorkspaceLinkItem } from '@/core/api/workspace'
import { useDocTypeStore } from '@/stores/doctype'
import { Plus, Trash2 } from '@lucide/vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import DocTypeCombobox from '@/components/DocTypeCombobox.vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

const doctypeNames = computed(() => dtStore.doctypes.filter(d => !d.is_child).map(d => d.name))

const linkItems = computed<WorkspaceLinkItem[]>(() => {
  try { return JSON.parse(widget.value.content ?? '[]') } catch { return [] }
})

function setLinks(val: WorkspaceLinkItem[]) {
  updateWidget('content', JSON.stringify(val))
}

function addLink() {
  setLinks([...linkItems.value, { label: t('New'), icon: '', type: 'DocType', link_to: '' }])
}

function removeLink(i: number) {
  const arr = [...linkItems.value]
  arr.splice(i, 1)
  setLinks(arr)
}

function updateLink(i: number, key: keyof WorkspaceLinkItem, value: string) {
  setLinks(linkItems.value.map((l, idx) => idx === i ? { ...l, [key]: value } : l))
}
</script>

<template>
  <Separator class="!mb-3" />
  <div class="flex items-center justify-between mb-3">
    <p class="font-semibold text-muted-foreground uppercase tracking-wide">{{ t('Links') }}</p>
    <Button variant="ghost" size="sm" @click="addLink">
      <Plus class="size-3" /> {{ t('Add') }}
    </Button>
  </div>
  <div class="mb-4 flex flex-col gap-2">
    <div v-if="linkItems.length === 0" class="py-3 text-center text-muted-foreground border rounded-md">
      {{ t('No links') }}
    </div>
    <div v-for="(link, i) in linkItems" :key="i" class="rounded-md border bg-muted/30 p-3 flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <span class="font-medium text-muted-foreground">{{ t('Link {n}', { n: i + 1 }) }}</span>
        <Button variant="ghost" size="icon-sm" class="text-muted-foreground hover:text-destructive" @click="removeLink(i)">
          <Trash2 class="size-3.5" />
        </Button>
      </div>
      <div class="flex items-center gap-2">
        <Input
          :model-value="link.icon"
          placeholder="Emoji 📋"
          class="w-20"
          @update:model-value="updateLink(i, 'icon', String($event))"
        />
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          class="flex-1 flex-wrap"
          :model-value="link.type"
          @update:model-value="(v) => v && updateLink(i, 'type', String(v))"
        >
          <ToggleGroupItem value="DocType" class="flex-1">DocType</ToggleGroupItem>
          <ToggleGroupItem value="Report" class="flex-1">{{ t('Report') }}</ToggleGroupItem>
          <ToggleGroupItem value="Page" class="flex-1">Page</ToggleGroupItem>
          <ToggleGroupItem value="URL" class="flex-1">URL</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <Input
        :model-value="link.label"
        :placeholder="t('Title')"
        class="w-full"
        @update:model-value="updateLink(i, 'label', String($event))"
      />
      <DocTypeCombobox
        v-if="link.type === 'DocType'"
        :model-value="link.link_to"
        :options="doctypeNames"
        class="w-full"
        @update:model-value="updateLink(i, 'link_to', $event)"
      />
      <Input
        v-else
        :model-value="link.link_to"
        :placeholder="t('URL or name...')"
        class="w-full"
        @update:model-value="updateLink(i, 'link_to', String($event))"
      />
      <Input
        :model-value="link.description ?? ''"
        :placeholder="t('Description (optional)')"
        class="w-full"
        @update:model-value="updateLink(i, 'description', String($event))"
      />
    </div>
  </div>
</template>
