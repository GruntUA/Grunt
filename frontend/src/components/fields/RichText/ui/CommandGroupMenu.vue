<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { activeIn, command, type CommandId } from '../editor/commands'
import { useRichEditorContext } from '../editor/useRichEditor'
import CommandMenuItem from './CommandMenuItem.vue'

// One toolbar control for a group of mutually exclusive commands (block
// style, alignment): the trigger shows the active one.
const props = defineProps<{
  group: CommandId[]
  label: string
  /** Show the active command's name next to its icon (on a wide toolbar). */
  showName?: boolean
}>()

const { t } = useI18n()
const { editor, refocus } = useRichEditorContext()

const current = computed(() => command(editor.value ? activeIn(editor.value, props.group) : props.group[0]!))
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        size="sm" variant="ghost" class="gap-0.5 px-1.5"
        :class="showName && 'text-foreground @lg:w-28 @lg:justify-between @lg:px-2'"
        :title="t(label)" :aria-label="t(label)"
      >
        <component :is="current.icon" :class="showName && '@lg:hidden'" />
        <span v-if="showName" class="hidden truncate @lg:inline">{{ t(current.label) }}</span>
        <ChevronDown class="hidden size-3 opacity-60 @md:block" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-56" @close-auto-focus="refocus">
      <CommandMenuItem v-for="id in group" :key="id" :id />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
