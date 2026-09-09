<script setup lang="ts">
import { ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PER_PAGE_OPTIONS } from '@/core/composables/useListViewState'

const props = withDefaults(defineProps<{
  page: number
  pages: number
  total: number
  perPage: number
  selectedCount?: number
  showPerPage?: boolean
  perPageOptions?: readonly number[]
}>(), {
  selectedCount: 0,
  showPerPage: true,
  perPageOptions: () => PER_PAGE_OPTIONS,
})

const emit = defineEmits<{
  'update:page': [value: number]
  'update:perPage': [value: number]
}>()

function go(p: number) {
  const clamped = Math.min(Math.max(p, 1), Math.max(props.pages, 1))
  if (clamped !== props.page) emit('update:page', clamped)
}

function onPerPage(v: unknown) {
  const n = Number(Array.isArray(v) ? v[0] : v)
  if (Number.isFinite(n) && n > 0) emit('update:perPage', n)
}
</script>

<template>
  <div class="flex flex-col-reverse items-center gap-3 px-1 py-3 text-xs sm:flex-row sm:justify-between">
    <div class="text-muted-foreground">
      {{ total }} {{ total === 1 ? 'запис' : 'записів' }}
      <span v-if="selectedCount"> · {{ selectedCount }} вибрано</span>
    </div>

    <div class="flex items-center gap-3 sm:gap-4">
      <div v-if="showPerPage" class="hidden items-center gap-2 sm:flex">
        <span class="text-muted-foreground">Рядків на сторінці</span>
        <Select :model-value="String(perPage)" @update:model-value="onPerPage">
          <SelectTrigger class="h-8 w-[4.5rem]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in perPageOptions" :key="opt" :value="String(opt)">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <span class="font-medium whitespace-nowrap">Сторінка {{ page }} з {{ Math.max(pages, 1) }}</span>

      <div class="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" :disabled="page <= 1" aria-label="Перша сторінка" @click="go(1)">
          <ChevronsLeft class="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" :disabled="page <= 1" aria-label="Попередня сторінка" @click="go(page - 1)">
          <ChevronLeft class="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" :disabled="page >= pages" aria-label="Наступна сторінка" @click="go(page + 1)">
          <ChevronRight class="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" :disabled="page >= pages" aria-label="Остання сторінка" @click="go(pages)">
          <ChevronsRight class="size-4" />
        </Button>
      </div>
    </div>
  </div>
</template>
