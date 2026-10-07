<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { canRunCommand, command, isCommandActive, runCommand, type CommandId } from '../editor/commands'
import { useEditorInstance } from '../editor/useRichEditor'

const props = defineProps<{ id: CommandId }>()

const { t } = useI18n()
const editor = useEditorInstance()

const cmd = computed(() => command(props.id))
const label = computed(() => t(cmd.value.label))
const active = computed(() => !!editor.value && isCommandActive(editor.value, props.id))
const enabled = computed(() => !!editor.value && canRunCommand(editor.value, props.id))
</script>

<template>
  <Button
    size="icon-sm" variant="ghost"
    :title="cmd.keys ? `${label} · ${cmd.keys}` : label"
    :aria-label="label"
    :aria-pressed="cmd.isActive ? active : undefined"
    :disabled="!enabled && !active"
    :class="[active && 'bg-accent text-primary', cmd.destructive && 'hover:text-destructive']"
    @click="runCommand(editor!, id)"
  >
    <component :is="cmd.icon" />
  </Button>
</template>
