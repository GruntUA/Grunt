<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, Copy, MoreHorizontal, PanelRightOpen, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

// The «⋯» menu of one child-table row - shared by the grid and the phone cards.
const emit = defineEmits<{ edit: []; duplicate: []; insert: [where: 'above' | 'below']; remove: [] }>()
const { t } = useI18n()
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button type="button" variant="ghost" size="icon" :aria-label="t('Row actions')" @click.stop>
        <MoreHorizontal />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem @click="emit('edit')">
        <PanelRightOpen /> {{ t('Edit') }}
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('duplicate')">
        <Copy /> {{ t('Duplicate row') }}
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('insert', 'above')">
        <ArrowUp /> {{ t('Insert row above') }}
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('insert', 'below')">
        <ArrowDown /> {{ t('Insert row below') }}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem variant="destructive" @click="emit('remove')">
        <Trash2 /> {{ t('Delete row') }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
