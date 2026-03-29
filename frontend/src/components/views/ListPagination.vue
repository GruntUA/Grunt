<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-vue-next'

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
  <div class="flex items-center justify-between">
    <p class="flex-1 text-sm text-muted-foreground">
      {{ (page - 1) * perPage + 1 }}–{{ Math.min(page * perPage, total) }} з {{ total }}
    </p>
    <div class="flex items-center gap-6 lg:gap-8">
      <p class="hidden sm:block text-sm font-medium text-foreground">
        Сторінка {{ page }} з {{ pages }}
      </p>
      <div class="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" class="text-foreground" :disabled="page <= 1" title="Перша сторінка" @click="emit('update:page', 1)">
          <ChevronsLeft class="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" class="text-foreground" :disabled="page <= 1" title="Попередня" @click="emit('update:page', page - 1)">
          <ChevronLeft class="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" class="text-foreground" :disabled="page >= pages" title="Наступна" @click="emit('update:page', page + 1)">
          <ChevronRight class="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" class="text-foreground" :disabled="page >= pages" title="Остання сторінка" @click="emit('update:page', pages)">
          <ChevronsRight class="size-4" />
        </Button>
      </div>
    </div>
  </div>
</template>
