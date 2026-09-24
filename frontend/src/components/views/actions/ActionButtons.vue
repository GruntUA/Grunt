<script setup lang="ts">
/**
 * Toolbar + primary actions of an action registry (core/actions.ts).
 * Toolbar actions of one `group` become a split button; the primary action
 * comes last, as the default (filled) button.
 */
import { computed } from 'vue'
import { ChevronDown, Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { actionButtonStyle, type ResolvedAction } from '@/core/actions'
import ActionIcon from './ActionIcon.vue'

const props = defineProps<{
  toolbar: ResolvedAction[]
  primary?: ResolvedAction[]
  /** Hide labelled toolbar buttons on narrow screens (the menu still has everything important). */
  compact?: boolean
}>()

type Slot = { kind: 'single'; action: ResolvedAction } | { kind: 'group'; name: string; items: ResolvedAction[] }

const slots = computed<Slot[]>(() => {
  const out: Slot[] = []
  const groups = new Map<string, ResolvedAction[]>()
  for (const action of props.toolbar) {
    if (!action.group) {
      out.push({ kind: 'single', action })
      continue
    }
    if (!groups.has(action.group)) {
      groups.set(action.group, [])
      out.push({ kind: 'group', name: action.group, items: groups.get(action.group)! })
    }
    groups.get(action.group)!.push(action)
  }
  return out.map((s) => (s.kind === 'group' && s.items.length === 1 ? { kind: 'single', action: s.items[0] } : s))
})

function style(action: ResolvedAction, fallback: 'outline' | 'default' = 'outline') {
  return actionButtonStyle(action.variant, fallback)
}

function title(action: ResolvedAction) {
  return action.shortcut ? `${action.label} (${action.shortcut})` : action.label
}
</script>

<template>
  <template v-for="slot in slots" :key="slot.kind === 'single' ? slot.action.id : `group:${slot.name}`">
    <Button
      v-if="slot.kind === 'single'"
      :size="slot.action.iconOnly ? 'icon-sm' : 'sm'"
      :variant="style(slot.action).variant"
      :class="[slot.action.iconOnly ? '' : 'gap-1.5', compact && !slot.action.iconOnly ? 'hidden sm:inline-flex' : '', style(slot.action).className]"
      :title="title(slot.action)"
      :aria-label="slot.action.label"
      :disabled="slot.action.disabled"
      @click="slot.action.run()"
    >
      <Loader2 v-if="slot.action.busy" class="size-4 animate-spin" />
      <ActionIcon v-else-if="slot.action.icon" :name="slot.action.icon" class="size-4" />
      <template v-if="!slot.action.iconOnly">{{ slot.action.label }}</template>
    </Button>

    <div v-else class="inline-flex" :class="compact ? 'hidden sm:inline-flex' : ''">
      <Button
        size="sm"
        :variant="style(slot.items[0]).variant"
        :class="['gap-1.5 rounded-r-none', style(slot.items[0]).className]"
        :title="slot.name"
        :disabled="slot.items[0].disabled"
        @click="slot.items[0].run()"
      >
        <ActionIcon v-if="slot.items[0].icon" :name="slot.items[0].icon" class="size-4" />
        {{ slot.items[0].label }}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button
            size="sm"
            :variant="style(slot.items[0]).variant"
            :class="['rounded-l-none border-l-0 px-2', style(slot.items[0]).className]"
            :aria-label="`${slot.name}: ще`"
          >
            <ChevronDown class="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            v-for="item in slot.items.slice(1)"
            :key="item.id"
            :disabled="item.disabled"
            @click="item.run()"
          >
            <ActionIcon v-if="item.icon" :name="item.icon" class="size-4" />
            {{ item.label }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </template>

  <Button
    v-for="action in primary ?? []"
    :key="action.id"
    size="sm"
    :variant="style(action, 'default').variant"
    :class="['gap-1.5', style(action, 'default').className]"
    :title="title(action)"
    :disabled="action.disabled || action.busy"
    @click="action.run()"
  >
    <Loader2 v-if="action.busy" class="size-4 animate-spin" />
    <ActionIcon v-else-if="action.icon" :name="action.icon" class="size-4" />
    {{ action.label }}
  </Button>
</template>
