<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps<{
  page: number
  pages: number
  total: number
  perPage: number
}>()

const emit = defineEmits<{
  'update:page': [value: number]
}>()
</script>

<template>
  <div v-if="pages > 1" class="mt-4 flex items-center justify-between">
    <p class="text-sm text-muted-foreground">
      {{ (page - 1) * perPage + 1 }}–{{ Math.min(page * perPage, total) }} з {{ total }}
    </p>
    <div class="flex items-center gap-1">
      <Button variant="outline" size="icon-sm" :disabled="page <= 1" @click="emit('update:page', page - 1)">
        <ChevronLeft class="size-4" />
      </Button>
      <span class="px-3 text-sm text-muted-foreground">{{ page }} / {{ pages }}</span>
      <Button variant="outline" size="icon-sm" :disabled="page >= pages" @click="emit('update:page', page + 1)">
        <ChevronRight class="size-4" />
      </Button>
    </div>
  </div>
</template>
