<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ALargeSmall, ChevronDown } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useRichEditorContext } from '../editor/useRichEditor'

// Toolbar font family and size pickers; the triggers show the current values.
const props = defineProps<{ documentStyle?: boolean }>()

const { t } = useI18n()
const { editor, refocus } = useRichEditorContext()

// The radio groups can't use '' for "no explicit font", hence the sentinel.
const DEFAULT = '__default__'

const FAMILIES = computed(() => [
  { label: t('Default'), value: DEFAULT },
  { label: 'Arial', value: 'Arial, sans-serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Times New Roman', value: '"Times New Roman", serif' },
  { label: 'Courier New', value: '"Courier New", monospace' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
])

// Document style targets print (the OutgoingLetter format lays the body out
// in pt), so its sizes are pt - «14» means 14pt, as in Word. Web text uses px.
const SIZES = computed(() => [
  { label: t('Auto'), value: DEFAULT },
  ...[10, 12, 14, 16, 18, 20, 24, 28, 36, 48].map(n => ({ label: String(n), value: `${n}${props.documentStyle ? 'pt' : 'px'}` })),
])

const textStyle = computed(() => editor.value?.getAttributes('textStyle') ?? {})
const family = computed(() => (textStyle.value.fontFamily as string | undefined) ?? DEFAULT)
const size = computed(() => (textStyle.value.fontSize as string | undefined) ?? DEFAULT)

// Fonts pasted from elsewhere may not be in the list - show them as they are.
const familyLabel = computed(() =>
  FAMILIES.value.find(f => f.value === family.value)?.label ?? family.value.split(',')[0]!.replace(/["']/g, ''))
const sizeLabel = computed(() =>
  size.value === DEFAULT ? t('Auto') : size.value.replace(/(px|pt)$/, ''))

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
      <Button
        size="sm" variant="ghost" class="gap-0.5 px-1.5 text-foreground @lg:w-32 @lg:justify-between @lg:px-2"
        :title="t('Font')" :aria-label="t('Font')"
      >
        <ALargeSmall class="@lg:hidden" />
        <span
          class="hidden truncate @lg:inline"
          :style="family !== DEFAULT ? { fontFamily: family } : undefined"
        >{{ familyLabel }}</span>
        <ChevronDown class="hidden size-3 opacity-60 @md:block" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-52" @close-auto-focus="refocus">
      <DropdownMenuRadioGroup :model-value="family" @update:model-value="(v) => setFamily(String(v))">
        <DropdownMenuRadioItem
          v-for="f in FAMILIES" :key="f.value" :value="f.value"
          :style="f.value !== DEFAULT ? { fontFamily: f.value } : undefined"
        >
          {{ f.label }}
        </DropdownMenuRadioItem>
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>

  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        size="sm" variant="ghost" class="w-14 justify-between gap-0.5 px-1.5 text-foreground tabular-nums"
        :title="t('Font size')" :aria-label="t('Font size')"
      >
        <span class="truncate">{{ sizeLabel }}</span>
        <ChevronDown class="size-3 opacity-60" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-28" @close-auto-focus="refocus">
      <DropdownMenuRadioGroup :model-value="size" @update:model-value="(v) => setSize(String(v))">
        <DropdownMenuRadioItem v-for="s in SIZES" :key="s.value" :value="s.value">{{ s.label }}</DropdownMenuRadioItem>
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
