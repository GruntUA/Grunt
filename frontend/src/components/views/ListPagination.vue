<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
const props = defineProps<{
  page: number
  pages: number
  total: number
  perPage: number
}>()

const emit = defineEmits<{
  'update:page': [value: number]
}>()

function goTo(p: number) {
  const clamped = Math.min(Math.max(p, 1), Math.max(props.pages, 1))
  if (clamped !== props.page) emit('update:page', clamped)
}

// Window of page numbers around the current page (max 5), always including first/last.
const pageWindow = computed<(number | '…')[]>(() => {
  const { page, pages } = props
  if (pages <= 1) return [1]
  const window = new Set<number>([1, pages, page, page - 1, page + 1].filter(p => p >= 1 && p <= pages))
  const sorted = [...window].sort((a, b) => a - b)
  const result: (number | '…')[] = []
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) result.push('…')
    result.push(p)
  })
  return result
})

const jumpInput = ref('')
function onJump() {
  const n = Number(jumpInput.value)
  if (Number.isFinite(n) && n >= 1) goTo(Math.round(n))
  jumpInput.value = ''
}
</script>

<template>
  <div class="flex items-center justify-between w-full py-2 px-1">
    <!-- Summary info -->
    <div class="hidden md:flex items-center gap-2">
        <span class="font-semibold text-muted-foreground/60 uppercase tracking-widest">Всього:</span>
        <Badge variant="secondary" class="!text-xs !font-semibold !px-2 !py-0.5 shadow-sm">
            {{ total }}
        </Badge>
    </div>

    <!-- Paginator -->
    <div class="flex-1 flex justify-center md:justify-end items-center gap-1">
        <Button variant="ghost" size="icon-sm" class="!size-9 !rounded-lg" :disabled="page <= 1" @click="goTo(1)">
          <ChevronsLeft class="size-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" class="!size-9 !rounded-lg" :disabled="page <= 1" @click="goTo(page - 1)">
          <ChevronLeft class="size-4" />
        </Button>

        <template v-for="(p, idx) in pageWindow" :key="idx">
          <span v-if="p === '…'" class="size-9 flex items-center justify-center text-muted-foreground/60">…</span>
          <Button
            v-else
            size="icon-sm"
            :variant="p === page ? 'default' : 'ghost'"
            class="!size-9 !rounded-lg !text-xs !font-semibold"
            :class="p === page ? '!shadow-md' : '!bg-muted/30 !text-muted-foreground hover:!bg-muted/50'"
            @click="goTo(p)"
          >{{ p }}</Button>
        </template>

        <Button variant="ghost" size="icon-sm" class="!size-9 !rounded-lg" :disabled="page >= pages" @click="goTo(page + 1)">
          <ChevronRight class="size-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" class="!size-9 !rounded-lg" :disabled="page >= pages" @click="goTo(pages)">
          <ChevronsRight class="size-4" />
        </Button>

        <Input
          v-model="jumpInput"
          type="number"
          min="1"
          :max="pages"
          placeholder="#"
          class="!h-9 !w-16 !text-xs !font-semibold !text-center"
          @keydown.enter="onJump"
        />
    </div>

    <!-- Mobile view summary -->
    <div class="md:hidden ml-4">
        <p class="font-semibold text-muted-foreground uppercase opacity-60">
            {{ page }} / {{ pages }}
        </p>
    </div>
  </div>
</template>
