<script setup lang="ts">
import { useI18n } from 'vue-i18n'
/** The «⋯» menu of an action registry: `menu` actions, one section per `group`. */
import { computed } from 'vue'
import { EllipsisVertical } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ResolvedAction } from '@/core/actions'
import ActionIcon from './ActionIcon.vue'

const { t } = useI18n()

const props = defineProps<{ actions: ResolvedAction[]; triggerVariant?: 'ghost' | 'outline' }>()

/** Sections keep the order of their first action; a separator between sections. */
const sections = computed(() => {
  const map = new Map<string, ResolvedAction[]>()
  for (const action of props.actions) {
    if (!map.has(action.group)) map.set(action.group, [])
    map.get(action.group)!.push(action)
  }
  return [...map.values()]
})
</script>

<template>
  <DropdownMenu v-if="actions.length">
    <DropdownMenuTrigger as-child>
      <Button :variant="triggerVariant ?? 'outline'" size="icon-sm" :aria-label="t('Actions')">
        <EllipsisVertical class="size-4" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="w-56" align="end">
      <template v-for="(section, i) in sections" :key="i">
        <DropdownMenuSeparator v-if="i > 0" />
        <DropdownMenuItem
          v-for="action in section"
          :key="action.id"
          :variant="action.variant === 'destructive' ? 'destructive' : 'default'"
          :disabled="action.disabled"
          @click="action.run()"
        >
          <ActionIcon v-if="action.icon" :name="action.icon" class="size-4" />
          <span>{{ action.label }}</span>
          <DropdownMenuShortcut v-if="action.shortcut">{{ action.shortcut }}</DropdownMenuShortcut>
        </DropdownMenuItem>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
