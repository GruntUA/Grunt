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
import { formatShortcut } from '@/core/shortcuts'
import ActionIcon from './ActionIcon.vue'

const { t } = useI18n()

const props = defineProps<{
  actions: ResolvedAction[]
  /** Toolbar of a compact ActionButtons: what it hides below `sm` is listed here instead. */
  toolbar?: ResolvedAction[]
  triggerVariant?: 'ghost' | 'outline'
}>()

/** Mirrors ActionButtons `compact`: labelled buttons and split-button groups. */
const narrowOnly = computed(() => {
  const toolbar = props.toolbar ?? []
  const groupSize = new Map<string, number>()
  for (const action of toolbar) {
    if (action.group) groupSize.set(action.group, (groupSize.get(action.group) ?? 0) + 1)
  }
  return toolbar.filter((a) => !a.iconOnly || (a.group && groupSize.get(a.group)! > 1))
})

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
  <DropdownMenu v-if="actions.length || narrowOnly.length">
    <DropdownMenuTrigger as-child>
      <Button :variant="triggerVariant ?? 'outline'" size="icon-sm" :class="{ 'sm:hidden': !actions.length }" :aria-label="t('Actions')">
        <EllipsisVertical class="size-4" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="w-56" align="end">
      <DropdownMenuItem
        v-for="action in narrowOnly"
        :key="action.id"
        class="sm:hidden"
        :variant="action.variant === 'destructive' ? 'destructive' : 'default'"
        :disabled="action.disabled || action.busy"
        @click="action.run()"
      >
        <ActionIcon v-if="action.icon" :name="action.icon" class="size-4" />
        <span>{{ action.label }}</span>
      </DropdownMenuItem>
      <DropdownMenuSeparator v-if="narrowOnly.length && actions.length" class="sm:hidden" />
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
          <DropdownMenuShortcut v-if="action.shortcut">{{ formatShortcut(action.shortcut) }}</DropdownMenuShortcut>
        </DropdownMenuItem>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
