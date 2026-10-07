<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import { NodeSelection } from '@tiptap/pm/state'
import type { Editor } from '@tiptap/core'
import { ChevronDown, Maximize, Replace, TextCursorInput } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { filesApi } from '@/core/api/files'
import { useToast } from '@/core/composables/useToast'
import { useRichEditorContext } from '../editor/useRichEditor'
import { IMAGE_SIZES } from '../extensions/image'
import CommandButton from './CommandButton.vue'

// The selected image: wrapping / centering, size, alt text, replace, delete.
const { t } = useI18n()
const toast = useToast()
const { editor, refocus, uploadTarget } = useRichEditorContext()

const NATURAL = 'natural'

const shouldShow = ({ editor: e }: { editor: Editor }) =>
  e.isEditable && e.view.hasFocus() && e.state.selection instanceof NodeSelection && e.isActive('image')

const attrs = () => editor.value?.getAttributes('image') ?? {}
const setAttrs = (values: Record<string, unknown>) => editor.value?.chain().focus().updateAttributes('image', values).run()

// Alt text
const altOpen = ref(false)
const alt = ref('')

function onAltOpen(open: boolean) {
  if (open) alt.value = attrs().alt ?? ''
  altOpen.value = open
}

function saveAlt() {
  setAttrs({ alt: alt.value.trim() || null })
  altOpen.value = false
}

// Replace keeps size, alignment and alt; only the picture changes.
const fileInput = ref<HTMLInputElement | null>(null)

async function replace(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const item = await filesApi.upload(file, uploadTarget())
    setAttrs({ src: item.url })
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err), t('Image upload failed'))
  }
}
</script>

<template>
  <BubbleMenu
    v-if="editor" :editor plugin-key="imageBubble" :should-show :options="{ placement: 'top', offset: 8 }"
    class="richtext-bubble z-20 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 text-muted-foreground shadow-md"
  >
    <CommandButton id="imageAlignLeft" />
    <CommandButton id="imageAlignCenter" />
    <CommandButton id="imageAlignRight" />
    <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button size="sm" variant="ghost" class="gap-1 px-1.5" :title="t('Size')" :aria-label="t('Size')">
          <Maximize />
          <span class="tabular-nums">{{ attrs().size ?? t('Auto') }}</span>
          <ChevronDown class="size-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" @close-auto-focus="refocus">
        <DropdownMenuRadioGroup
          :model-value="attrs().size ?? NATURAL"
          @update:model-value="(v) => setAttrs({ size: v === NATURAL ? null : v })"
        >
          <DropdownMenuRadioItem :value="NATURAL">{{ t('Original size') }}</DropdownMenuRadioItem>
          <DropdownMenuRadioItem v-for="s in IMAGE_SIZES" :key="s" :value="s">
            {{ t('{size} of text width', { size: s }) }}
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>

    <Popover :open="altOpen" @update:open="onAltOpen">
      <PopoverTrigger as-child>
        <Button size="icon-sm" variant="ghost" :class="attrs().alt && 'text-primary'" :title="t('Alt text')" :aria-label="t('Alt text')">
          <TextCursorInput />
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-80 p-2">
        <p class="mb-1 font-medium text-muted-foreground">{{ t('Alt text') }}</p>
        <p class="mb-2 text-muted-foreground">{{ t('Describes the image for screen readers and search engines.') }}</p>
        <div class="flex gap-2">
          <Input v-model="alt" class="h-8 flex-1" :aria-label="t('Alt text')" @keydown.enter.prevent="saveAlt" />
          <Button size="sm" @click="saveAlt">OK</Button>
        </div>
      </PopoverContent>
    </Popover>

    <Button size="icon-sm" variant="ghost" :title="t('Replace image')" :aria-label="t('Replace image')" @click="fileInput?.click()">
      <Replace />
    </Button>
    <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="replace" />

    <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />
    <CommandButton id="deleteSelection" />
  </BubbleMenu>
</template>
