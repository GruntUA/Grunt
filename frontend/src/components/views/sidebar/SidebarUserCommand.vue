<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Colleague } from '@/types'
import type { DocSidebarState } from './useDocSidebar'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'

// User search list shared by the assign / share pickers.
const props = defineProps<{ sb: DocSidebarState; exclude?: string[] }>()
const emit = defineEmits<{ select: [email: string] }>()

const { t } = useI18n()
const users = ref<Colleague[]>([])

onMounted(async () => {
  users.value = await props.sb.searchUsers('')
})

function initials(u: Colleague): string {
  return (u.full_name || u.email).slice(0, 2).toUpperCase()
}
</script>

<template>
  <Command>
    <CommandInput :placeholder="t('Search user...')" />
    <CommandList class="max-h-64">
      <CommandEmpty>{{ t('No users found') }}</CommandEmpty>
      <CommandGroup>
        <CommandItem
          v-for="u in users"
          :key="u.email"
          :value="u.email"
          :disabled="exclude?.includes(u.email)"
          @select="emit('select', u.email)"
        >
          <Avatar class="size-6">
            <AvatarFallback class="text-[10px]">{{ initials(u) }}</AvatarFallback>
          </Avatar>
          <div class="flex min-w-0 flex-col">
            <span class="truncate">{{ u.full_name || u.email }}</span>
            <span v-if="u.full_name" class="truncate text-xs text-muted-foreground">{{ u.email }}</span>
          </div>
        </CommandItem>
      </CommandGroup>
      <template v-if="$slots.footer">
        <CommandSeparator />
        <CommandGroup>
          <slot name="footer" />
        </CommandGroup>
      </template>
    </CommandList>
  </Command>
</template>
