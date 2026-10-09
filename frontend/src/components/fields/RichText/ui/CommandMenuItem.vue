<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ContextMenuItem, ContextMenuShortcut } from '@/components/ui/context-menu'
import { DropdownMenuItem, DropdownMenuShortcut } from '@/components/ui/dropdown-menu'
import { canRunCommand, command, isCommandActive, runCommand, type CommandId } from '../editor/commands'
import { useEditorInstance } from '../editor/useRichEditor'

// `context` - an item of the right-click menu instead of a dropdown.
const props = defineProps<{ id: CommandId; context?: boolean }>()

const { t } = useI18n()
const editor = useEditorInstance()

const Item = computed(() => (props.context ? ContextMenuItem : DropdownMenuItem))
const Shortcut = computed(() => (props.context ? ContextMenuShortcut : DropdownMenuShortcut))

const cmd = computed(() => command(props.id))
const active = computed(() => !!editor.value && isCommandActive(editor.value, props.id))
const enabled = computed(() => !!editor.value && canRunCommand(editor.value, props.id))
</script>

<template>
  <component
    :is="Item"
    :disabled="!enabled && !active"
    :variant="cmd.destructive ? 'destructive' : 'default'"
    :class="active && 'bg-accent/60'"
    @select="runCommand(editor!, id)"
  >
    <component :is="cmd.icon" />
    {{ t(cmd.label) }}
    <component :is="Shortcut" v-if="cmd.keys">{{ cmd.keys }}</component>
  </component>
</template>
