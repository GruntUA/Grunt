<script setup lang="ts">
import { computed } from 'vue'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import PvAvatar from 'primevue/avatar'

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
  <TooltipProvider :delay-duration="100">
    <div v-if="users.length > 0" class="flex items-center -space-x-2 group">
      <div v-for="user in visible" :key="user.email"
        class="relative transition-transform duration-200 hover:scale-110 hover:z-20 cursor-default">
        <Tooltip>
          <TooltipTrigger as-child>
            <PvAvatar
              :label="initials(user.full_name)"
              shape="circle"
              :pt="{ root: { class: 'size-7 border-2 border-background ring-2 ring-transparent group-hover:ring-white/10 shadow-sm transition-all text-[10px] font-bold text-white', style: { backgroundColor: user.color } } }"
            />
          </TooltipTrigger>
          <TooltipContent side="bottom" class="text-xs">
            <p class="font-bold">{{ user.full_name }}</p>
            <p class="text-[10px] opacity-70">{{ user.email }}</p>
          </TooltipContent>
        </Tooltip>
      </div>

      <!-- Overflow indicator -->
      <PvAvatar
        v-if="hidden > 0"
        :label="`+${hidden}`"
        shape="circle"
        :pt="{ root: { class: 'size-7 border-2 border-background z-0 bg-muted text-[10px] font-bold text-muted-foreground' } }"
      />
    </div>
  </TooltipProvider>
</template>
