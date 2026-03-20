<script setup lang="ts">
import { ref } from 'vue'

export interface Column {
  key: string
  label: string
  sortable?: boolean
}

withDefaults(defineProps<{
  columns: Column[]
  rows: Record<string, unknown>[]
  loading?: boolean
}>(), { loading: false })

const emit = defineEmits<{
  sort: [key: string, order: 'asc' | 'desc']
  rowClick: [row: Record<string, unknown>]
}>()

const sortKey = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')

function onSort(col: Column) {
  if (!col.sortable) return
  if (sortKey.value === col.key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = col.key
    sortOrder.value = 'asc'
  }
  emit('sort', sortKey.value, sortOrder.value)
}
</script>

<template>
  <div class="overflow-hidden border border-[--grunt-border] rounded-[--grunt-radius-md] bg-[--grunt-surface]">
    <table class="min-w-full divide-y divide-[--grunt-border]">
      <thead class="bg-[--grunt-surface-secondary]">
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :class="['px-4 py-3 text-left text-xs font-semibold text-[--grunt-text-secondary] uppercase tracking-wide', col.sortable ? 'cursor-pointer hover:text-[--grunt-text-primary] select-none' : '']"
            @click="onSort(col)"
          >
            {{ col.label }}
            <span v-if="col.sortable && sortKey === col.key" class="ml-1">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-[--grunt-border]">
        <!-- Loading skeleton -->
        <template v-if="loading">
          <tr v-for="n in 3" :key="n" class="animate-pulse">
            <td v-for="col in columns" :key="col.key" class="px-4 py-3">
              <div class="h-4 bg-gray-200 rounded w-3/4" />
            </td>
          </tr>
        </template>
        <!-- Empty -->
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length" class="px-4 py-10 text-center text-sm text-[--grunt-text-muted]">
            Немає даних
          </td>
        </tr>
        <!-- Rows -->
        <template v-else>
          <tr
            v-for="(row, i) in rows"
            :key="(row.id as string) ?? i"
            class="hover:bg-[--grunt-surface-secondary] transition-colors cursor-pointer"
            @click="emit('rowClick', row)"
          >
            <td v-for="col in columns" :key="col.key" class="px-4 py-3 text-sm text-[--grunt-text-primary]">
              <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                {{ row[col.key] ?? '—' }}
              </slot>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
