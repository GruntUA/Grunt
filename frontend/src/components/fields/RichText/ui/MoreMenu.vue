<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ALargeSmall, Ellipsis, Type } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useRichEditorContext } from '../editor/useRichEditor'
import CommandMenuItem from './CommandMenuItem.vue'

// "⋯": rarely used formatting - inline code, indent, font family and size.
const props = defineProps<{ documentStyle?: boolean }>()

const { t } = useI18n()
const { editor, refocus } = useRichEditorContext()

// The radio groups can't use '' for "no explicit font", hence the sentinel.
const DEFAULT = '__default__'

const FAMILIES = [
  { label: t('Default'), value: DEFAULT },
  { label: 'Arial', value: 'Arial, sans-serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Times New Roman', value: '"Times New Roman", serif' },
  { label: 'Courier New', value: '"Courier New", monospace' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
]

// Document style targets print (the OutgoingLetter format lays the body out
// in pt), so its sizes are pt - «14» means 14pt, as in Word. Web text uses px.
const SIZES = computed(() => [
  { label: t('Auto'), value: DEFAULT },
  ...[10, 12, 14, 16, 18, 20, 24, 28, 36, 48].map(n => ({ label: String(n), value: `${n}${props.documentStyle ? 'pt' : 'px'}` })),
])

const textStyle = () => editor.value?.getAttributes('textStyle') ?? {}

function setFamily(value: string) {
  const chain = editor.value?.chain().focus()
  ;(value === DEFAULT ? chain?.unsetFontFamily() : chain?.setFontFamily(value))?.run()
}

function setSize(value: string) {
  const chain = editor.value?.chain().focus()
  ;(value === DEFAULT ? chain?.unsetFontSize() : chain?.setFontSize(value))?.run()
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button size="icon-sm" variant="ghost" :title="t('More')" :aria-label="t('More')">
        <Ellipsis />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-60" @close-auto-focus="refocus">
      <CommandMenuItem id="highlight" />
      <CommandMenuItem id="superscript" />
      <CommandMenuItem id="subscript" />
      <CommandMenuItem id="code" />
      <CommandMenuItem id="indent" />
      <CommandMenuItem id="outdent" />
      <DropdownMenuSeparator />
      <DropdownMenuSub>
        <DropdownMenuSubTrigger><ALargeSmall /> {{ t('Font') }}</DropdownMenuSubTrigger>
        <DropdownMenuSubContent>
          <DropdownMenuRadioGroup :model-value="textStyle().fontFamily ?? DEFAULT" @update:model-value="(v) => setFamily(String(v))">
            <DropdownMenuRadioItem
              v-for="f in FAMILIES" :key="f.value" :value="f.value"
              :style="f.value !== DEFAULT ? { fontFamily: f.value } : undefined"
            >
              {{ f.label }}
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger><Type /> {{ t('Font size') }}</DropdownMenuSubTrigger>
        <DropdownMenuSubContent>
          <DropdownMenuRadioGroup :model-value="textStyle().fontSize ?? DEFAULT" @update:model-value="(v) => setSize(String(v))">
            <DropdownMenuRadioItem v-for="s in SIZES" :key="s.value" :value="s.value">{{ s.label }}</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuSubContent>
      </DropdownMenuSub>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
