<script setup lang="ts">
import { computed } from 'vue'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'

const props = withDefaults(
  defineProps<{
    users: PresenceUser[]
    max?: number
  }>(),
  { max: 5 },
)

const visible = computed(() => props.users.slice(0, props.max))
const hidden = computed(() => Math.max(0, props.users.length - props.max))
</script>

<template>
    <div v-if="users.length > 0" class="flex items-center -space-x-2 group">
      <Tooltip v-for="user in visible" :key="user.email">
        <TooltipTrigger as-child>
          <div class="relative transition-transform duration-200 hover:scale-110 hover:z-20 cursor-default">
            <Avatar class="size-7 border-2 border-background ring-2 ring-transparent group-hover:ring-white/10 shadow-sm transition-all">
              <AvatarFallback class="text-[10px] font-bold text-white" :style="{ backgroundColor: user.color }">
                {{ initials(user.full_name) }}
              </AvatarFallback>
            </Avatar>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom">{{ user.full_name }}</TooltipContent>
      </Tooltip>

      <!-- Overflow indicator -->
      <Avatar v-if="hidden > 0" class="size-7 border-2 border-background z-0">
        <AvatarFallback class="bg-muted text-[10px] font-bold text-muted-foreground">+{{ hidden }}</AvatarFallback>
      </Avatar>
    </div>
</template>
