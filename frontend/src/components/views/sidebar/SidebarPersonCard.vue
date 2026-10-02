<script setup lang="ts">
import type { DocSidebarState } from './useDocSidebar'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'

// Hover card for a person in the sidebar: the trigger is the slot (an avatar
// or a name), the card shows the full name, email and an optional note.
defineProps<{
  sb: DocSidebarState
  email: string | null | undefined
  /** Extra line under the email, e.g. "assigned 2 days ago". */
  meta?: string
}>()
</script>

<template>
  <HoverCard :open-delay="300" :close-delay="100">
    <HoverCardTrigger as-child>
      <slot />
    </HoverCardTrigger>
    <HoverCardContent align="start" class="w-72">
      <div class="flex gap-3">
        <Avatar class="size-10">
          <AvatarImage v-if="sb.personAvatar(email)" :src="sb.personAvatar(email)!" />
          <AvatarFallback>{{ sb.personInitials(email) }}</AvatarFallback>
        </Avatar>
        <div class="flex min-w-0 flex-col gap-0.5">
          <span class="text-sm font-semibold break-words">{{ sb.personName(email) }}</span>
          <span v-if="email && sb.personName(email) !== email" class="truncate text-xs text-muted-foreground">
            {{ email }}
          </span>
          <span v-if="meta" class="text-xs text-muted-foreground">{{ meta }}</span>
        </div>
      </div>
    </HoverCardContent>
  </HoverCard>
</template>
