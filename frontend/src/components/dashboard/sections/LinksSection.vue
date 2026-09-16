<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { WorkspaceLinkItem } from '@/core/api/workspace'
import { useDocTypeStore } from '@/stores/doctype'
import { Plus, Trash2 } from '@lucide/vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

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
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Links') }}</label>
      <button class="flex items-center gap-1 text-primary hover:underline" @click="addLink">
        <Plus class="size-3" /> {{ t('Add') }}
      </button>
    </div>
    <div v-if="linkItems.length === 0" class="py-3 text-center text-muted-foreground border rounded-md">
      {{ t('No links') }}
    </div>
    <div v-for="(link, i) in linkItems" :key="i" class="rounded-md border bg-muted/30 p-3 space-y-2">
      <div class="flex items-center justify-between">
        <span class="font-medium text-muted-foreground">{{ t('Link {n}', { n: i + 1 }) }}</span>
        <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeLink(i)">
          <Trash2 class="size-3.5" />
        </button>
      </div>
      <div class="grid grid-cols-2 gap-1.5">
        <input :value="link.icon" class="h-7 px-2.5 rounded border bg-background focus:outline-none" placeholder="Emoji 📋" @input="updateLink(i, 'icon', ($event.target as HTMLInputElement).value)" />
        <select :value="link.type" class="h-7 px-2 rounded border bg-background focus:outline-none" @change="updateLink(i, 'type', ($event.target as HTMLSelectElement).value)">
          <option value="DocType">DocType</option>
          <option value="Report">{{ t('Report') }}</option>
          <option value="Page">Page</option>
          <option value="URL">URL</option>
        </select>
      </div>
      <input :value="link.label" class="w-full h-7 px-2.5 rounded border bg-background focus:outline-none" :placeholder="t('Title')" @input="updateLink(i, 'label', ($event.target as HTMLInputElement).value)" />
      <select
        v-if="link.type === 'DocType'"
        :value="link.link_to"
        class="w-full h-7 px-2 rounded border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        @change="updateLink(i, 'link_to', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">{{ t('— Select —') }}</option>
        <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">{{ dt.label }}</option>
      </select>
      <input
        v-else
        :value="link.link_to"
        class="w-full h-7 px-2.5 rounded border bg-background focus:outline-none"
        :placeholder="t('URL or name...')"
        @input="updateLink(i, 'link_to', ($event.target as HTMLInputElement).value)"
      />
      <input :value="link.description" class="w-full h-7 px-2.5 rounded border bg-background focus:outline-none" :placeholder="t('Description (optional)')" @input="updateLink(i, 'description', ($event.target as HTMLInputElement).value)" />
    </div>
  </div>
</template>
