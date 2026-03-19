<template>
  <div class="overflow-hidden shadow ring-1 ring-black ring-opacity-5 sm:rounded-lg">
    <table class="min-w-full divide-y divide-gray-300">
      <thead class="bg-gray-50">
        <tr>
          <th 
            v-for="col in columns" 
            :key="col.key" 
            scope="col" 
            class="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-6"
          >
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-200 bg-white">
        <tr v-if="!data || data.length === 0">
          <td :colspan="columns.length" class="py-12 text-center text-sm text-gray-500">
            Немає даних
          </td>
        </tr>
        <tr v-for="item in data" :key="item[trackBy]" class="hover:bg-gray-50 transition-colors">
          <td 
            v-for="col in columns" 
            :key="col.key" 
            class="whitespace-nowrap py-4 pl-4 pr-3 text-sm text-gray-900 sm:pl-6"
          >
            <slot :name="`cell-${col.key}`" :item="item" :value="item[col.key]">
              {{ item[col.key] }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
export interface ColumnInfo {
  key: string
  label: string
}

const props = withDefaults(defineProps<{
  columns: ColumnInfo[]
  data: any[]
  trackBy?: string
}>(), {
  trackBy: 'id'
})
</script>
