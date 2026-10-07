<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { Link as LinkIcon, Link2Off } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useEditorInstance } from '../editor/useRichEditor'

// Link button + its URL form. Used by the toolbar, the selection bubble and
// (as "Edit link") the link bubble.
const props = defineProps<{ icon?: Component; label?: string }>()

const { t } = useI18n()
const title = computed(() => t(props.label ?? 'Link'))
const editor = useEditorInstance()

const open = ref(false)
const url = ref('')

function onOpen(value: boolean) {
  if (value) url.value = editor.value?.getAttributes('link').href ?? ''
  open.value = value
}

function apply() {
  const href = url.value.trim()
  const chain = editor.value?.chain().focus().extendMarkRange('link')
  ;(href ? chain?.setLink({ href }) : chain?.unsetLink())?.run()
  open.value = false
}

function remove() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  open.value = false
}
</script>

<template>
  <Popover :open @update:open="onOpen">
    <PopoverTrigger as-child>
      <Button
        size="icon-sm" variant="ghost"
        :title :aria-label="title" :aria-pressed="icon ? undefined : editor?.isActive('link')"
        :class="!icon && editor?.isActive('link') && 'bg-accent text-primary'"
      >
        <component :is="icon ?? LinkIcon" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-80 p-2">
      <p class="mb-2 font-medium text-muted-foreground">{{ t('Link') }}</p>
      <div class="flex gap-2">
        <Input v-model="url" placeholder="https://…" class="h-8 flex-1" :aria-label="t('Link URL')" @keydown.enter.prevent="apply" />
        <Button size="sm" @click="apply">OK</Button>
        <Button
          v-if="editor?.isActive('link')" size="icon-sm" variant="ghost" class="text-destructive hover:text-destructive"
          :title="t('Remove link')" :aria-label="t('Remove link')" @click="remove"
        >
          <Link2Off />
        </Button>
      </div>
    </PopoverContent>
  </Popover>
</template>
