<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Ellipsis } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useRichEditorContext } from '../editor/useRichEditor'
import CommandMenuItem from './CommandMenuItem.vue'

// "⋯": rarely used formatting - inline code, scripts, indent.
const { t } = useI18n()
const { refocus } = useRichEditorContext()
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button size="icon-sm" variant="ghost" :title="t('More')" :aria-label="t('More')">
        <Ellipsis />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-56" @close-auto-focus="refocus">
      <CommandMenuItem id="highlight" />
      <CommandMenuItem id="superscript" />
      <CommandMenuItem id="subscript" />
      <CommandMenuItem id="code" />
      <CommandMenuItem id="indent" />
      <CommandMenuItem id="outdent" />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
