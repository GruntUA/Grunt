<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

// The signed-in user's avatar, name and email: the sidebar's user button and its menu header.
const auth = useAuthStore()

function initials(name: string) { return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() }
</script>

<template>
  <Avatar class="size-8 rounded-lg">
    <AvatarImage v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" />
    <AvatarFallback class="rounded-lg">{{ auth.user ? initials(auth.user.full_name) : '?' }}</AvatarFallback>
  </Avatar>
  <div class="grid flex-1 text-left leading-tight">
    <span class="truncate font-medium">{{ auth.user?.full_name }}</span>
    <span class="truncate text-muted-foreground">{{ auth.user?.email }}</span>
  </div>
</template>
