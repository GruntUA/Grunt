<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { DropdownMenuItem, DropdownMenuShortcut } from '@/components/ui/dropdown-menu'
import { canRunCommand, command, isCommandActive, runCommand, type CommandId } from '../editor/commands'
import { useEditorInstance } from '../editor/useRichEditor'

const props = defineProps<{ id: CommandId }>()

const { t } = useI18n()
const editor = useEditorInstance()

const cmd = computed(() => command(props.id))
const active = computed(() => !!editor.value && isCommandActive(editor.value, props.id))
const enabled = computed(() => !!editor.value && canRunCommand(editor.value, props.id))
</script>

<template>
  <DropdownMenuItem
    :disabled="!enabled && !active"
    :variant="cmd.destructive ? 'destructive' : 'default'"
    :class="active && 'bg-accent/60'"
    @select="runCommand(editor!, id)"
  >
    <component :is="cmd.icon" />
    {{ t(cmd.label) }}
    <DropdownMenuShortcut v-if="cmd.keys">{{ cmd.keys }}</DropdownMenuShortcut>
  </DropdownMenuItem>
</template>
