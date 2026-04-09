<script setup lang="ts">
import { ref, watch } from 'vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Search, Settings2 } from 'lucide-vue-next'
import type { ListColumn } from '@/core/composables/useListColumns'

defineProps<{
  allColumns: ListColumn[]
  hiddenCols: string[]
}>()

const emit = defineEmits<{
  search: [value: string]
  toggleCol: [key: string]
}>()

const search = ref('')
const showColMenu = ref(false)

let debounceTimer: ReturnType<typeof setTimeout>
watch(search, (v) => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => emit('search', v), 400)
})
</script>

<template>
  <div class="flex items-center gap-3 mb-3">
    <div class="relative w-72">
      <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
      <Input v-model="search" placeholder="Пошук..." class="pl-9" />
    </div>

    <div class="ml-auto">
      <DropdownMenu v-model:open="showColMenu">
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" size="icon-sm" title="Колонки">
            <Settings2 class="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="p-2 min-w-40">
          <label
            v-for="col in allColumns"
            :key="col.key"
            class="flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent rounded-md cursor-pointer transition-colors"
          >
            <Checkbox
              :checked="!hiddenCols.includes(col.key)"
              @update:checked="emit('toggleCol', col.key)"
            />
            {{ col.label }}
          </label>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </div>
</template>
