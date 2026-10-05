<script setup lang="ts">
import { useI18n } from 'vue-i18n'
/**
 * Toolbar + primary actions of an action registry (core/actions.ts).
 * Toolbar actions of one `group` become a split button (shadcn ButtonGroup:
 * the first action as the button, the rest in its dropdown); the primary action
 * comes last, as the default (filled) button.
 */
import { computed } from 'vue'
import { ChevronDown, Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupSeparator } from '@/components/ui/button-group'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import ShortcutKbd from '@/components/ShortcutKbd.vue'
import { actionButtonStyle, type ResolvedAction } from '@/core/actions'
import ActionIcon from './ActionIcon.vue'

const { t } = useI18n()

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

/** Destructive actions stay red inside a group's dropdown. */
function menuVariant(action: ResolvedAction) {
  return style(action).variant === 'destructive' ? 'destructive' : 'default'
}

/** Actions with a shortcut get a tooltip with key caps instead of a native title. */
function title(action: ResolvedAction) {
  return action.shortcut ? undefined : action.label
}
</script>

<template>
  <template v-for="slot in slots" :key="slot.kind === 'single' ? slot.action.id : `group:${slot.name}`">
    <Tooltip v-if="slot.kind === 'single'" :disabled="!slot.action.shortcut">
      <TooltipTrigger as-child>
        <Button
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
      </TooltipTrigger>
      <TooltipContent v-if="slot.action.shortcut" class="flex items-center gap-2">
        {{ slot.action.label }}
        <ShortcutKbd :shortcut="slot.action.shortcut" />
      </TooltipContent>
    </Tooltip>

    <ButtonGroup v-else :aria-label="slot.name" :class="compact ? 'hidden sm:flex' : ''">
      <Button
        size="sm"
        :variant="style(slot.items[0]).variant"
        :class="['gap-1.5', style(slot.items[0]).className]"
        :title="slot.name"
        :disabled="slot.items[0].disabled || slot.items[0].busy"
        @click="slot.items[0].run()"
      >
        <Loader2 v-if="slot.items[0].busy" class="size-4 animate-spin" />
        <ActionIcon v-else-if="slot.items[0].icon" :name="slot.items[0].icon" class="size-4" />
        {{ slot.items[0].label }}
      </Button>
      <!-- Filled buttons have no border to split them - shadcn puts a separator between. -->
      <ButtonGroupSeparator v-if="style(slot.items[0]).variant !== 'outline'" />
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button
            size="sm"
            :variant="style(slot.items[0]).variant"
            :class="['!px-2', style(slot.items[0]).className]"
            :aria-label="`${slot.name}: ${t('more')}`"
          >
            <ChevronDown class="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="min-w-44">
          <DropdownMenuItem
            v-for="item in slot.items.slice(1)"
            :key="item.id"
            :variant="menuVariant(item)"
            :disabled="item.disabled || item.busy"
            @click="item.run()"
          >
            <Loader2 v-if="item.busy" class="size-4 animate-spin" />
            <ActionIcon v-else-if="item.icon" :name="item.icon" class="size-4" />
            {{ item.label }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </ButtonGroup>
  </template>

  <Tooltip v-for="action in primary ?? []" :key="action.id" :disabled="!action.shortcut">
    <TooltipTrigger as-child>
      <Button
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
    </TooltipTrigger>
    <TooltipContent v-if="action.shortcut" class="flex items-center gap-2">
      {{ action.label }}
      <ShortcutKbd :shortcut="action.shortcut" />
    </TooltipContent>
  </Tooltip>
</template>
