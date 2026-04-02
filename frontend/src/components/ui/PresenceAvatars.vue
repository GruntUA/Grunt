<script setup lang="ts">
import { computed } from 'vue'
import type { PresenceUser } from '@/core/composables/usePresence'
import { initials } from '@/core/composables/usePresence'

const props = withDefaults(
  defineProps<{
    users: PresenceUser[]
    max?: number
  }>(),
  { max: 4 },
)

const visible = computed(() => props.users.slice(0, props.max))
const hidden = computed(() => Math.max(0, props.users.length - props.max))
</script>

<template>
  <div v-if="users.length > 0" class="flex items-center -space-x-2">
    <div
      v-for="user in visible"
      :key="user.email"
      class="size-7 rounded-full ring-2 ring-background flex items-center justify-center text-[11px] font-bold text-white select-none shrink-0 cursor-default transition-transform hover:scale-110 hover:z-10"
      :style="{ backgroundColor: user.color }"
      :title="user.full_name"
    >
      {{ initials(user.full_name) }}
    </div>

    <div
      v-if="hidden > 0"
      class="size-7 rounded-full ring-2 ring-background bg-muted flex items-center justify-center text-[11px] font-semibold text-muted-foreground shrink-0"
      :title="`+${hidden} інших`"
    >
      +{{ hidden }}
    </div>
  </div>
</template>
