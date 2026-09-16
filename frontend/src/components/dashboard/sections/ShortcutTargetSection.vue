<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { docsApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
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
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Link type') }}</p>
  <div class="mb-4">
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      class="w-full flex-wrap"
      :model-value="widget.link_type ?? 'DocType'"
      @update:model-value="(v) => v && updateWidget('link_type', v)"
    >
      <ToggleGroupItem v-for="lt in LINK_TYPES" :key="lt.value" :value="lt.value" class="flex-1">{{ lt.label }}</ToggleGroupItem>
    </ToggleGroup>
  </div>

  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Target') }}</label>
    <div v-if="linkSearchDoctype" class="relative">
      <Input
        :model-value="linkQuery"
        :placeholder="t('Search {dt}...', { dt: linkSearchDoctype })"
        autocomplete="off"
        class="w-full"
        @update:model-value="onLinkInput(String($event))"
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
    <Input
      v-else
      :model-value="widget.doctype"
      placeholder="https://…"
      class="w-full"
      @update:model-value="updateWidget('doctype', $event)"
    />
  </div>
</template>
