<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { docsApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const LINK_TYPES = computed(() => [
  { value: 'DocType', label: t('DocType (list)') },
  { value: 'Report',  label: t('Report') },
  { value: 'Page',    label: t('Page') },
  { value: 'URL',     label: t('External URL') },
])

const linkQuery = ref('')
const linkResults = ref<LinkSearchItem[]>([])
const linkOpen = ref(false)
let linkTimer: ReturnType<typeof setTimeout>
let linkBlurTimer: ReturnType<typeof setTimeout>

const linkSearchDoctype = computed(() => {
  const lt = widget.value.link_type
  return (lt === 'DocType' || lt === 'Report' || lt === 'Page') ? lt : null
})

watch(() => widget.value.doctype, (v) => { linkQuery.value = v ?? '' }, { immediate: true })
watch(linkSearchDoctype, () => { linkQuery.value = widget.value.doctype ?? '' })

async function onLinkInput(val: string) {
  linkQuery.value = val
  updateWidget('doctype', val)
  if (!linkSearchDoctype.value) return
  clearTimeout(linkTimer)
  linkTimer = setTimeout(async () => {
    try {
      linkResults.value = await docsApi.linkSearch(linkSearchDoctype.value!, val)
      linkOpen.value = true
    } catch { linkResults.value = [] }
  }, val ? 250 : 0)
}

async function onLinkFocus() {
  clearTimeout(linkBlurTimer)
  if (!linkSearchDoctype.value) return
  try {
    linkResults.value = await docsApi.linkSearch(linkSearchDoctype.value, linkQuery.value)
    linkOpen.value = true
  } catch { linkResults.value = [] }
}

function onLinkBlur() {
  linkBlurTimer = setTimeout(() => { linkOpen.value = false }, 200)
}

function selectLink(item: LinkSearchItem) {
  linkQuery.value = item.title
  linkOpen.value = false
  updateWidget('doctype', item.name)
}
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Target') }}</label>
    <div v-if="linkSearchDoctype" class="relative">
      <input
        :value="linkQuery"
        class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        :placeholder="t('Search {dt}...', { dt: linkSearchDoctype })"
        autocomplete="off"
        @input="onLinkInput(($event.target as HTMLInputElement).value)"
        @focus="onLinkFocus"
        @blur="onLinkBlur"
      />
      <div
        v-if="linkOpen && linkResults.length"
        class="absolute left-0 right-0 top-full mt-1 z-50 bg-popover border border-border rounded-md shadow-md max-h-48 overflow-y-auto"
      >
        <button
          v-for="item in linkResults"
          :key="item.name"
          type="button"
          class="w-full text-left px-3 py-1.5 hover:bg-accent/50 transition-colors"
          @mousedown.prevent="selectLink(item)"
        >{{ item.title }}</button>
      </div>
    </div>
    <input
      v-else
      :value="widget.doctype"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      placeholder="https://…"
      @change="updateWidget('doctype', ($event.target as HTMLInputElement).value)"
    />
  </div>

  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Link type') }}</label>
    <div class="grid grid-cols-2 gap-1">
      <button
        v-for="lt in LINK_TYPES" :key="lt.value"
        :class="[
          'px-2.5 py-1.5 rounded-md border transition-colors',
          widget.link_type === lt.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
        ]"
        @click="updateWidget('link_type', lt.value)"
      >{{ lt.label }}</button>
    </div>
  </div>
</template>
