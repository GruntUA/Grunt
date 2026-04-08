<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import DataTable from '@/components/views/DataTable.vue'

const props = defineProps<{
  dt: any
  groupedRows: any[]
  columns: any[]
  collapsedGroups: Set<string>
  sortKey: string
  sortOrder: 'asc' | 'desc'
  selection: any
  groupByField: any
}>()

const emit = defineEmits<{
  (e: 'toggleGroup', key: string): void
  (e: 'sort', key: string): void
  (e: 'selectAll'): void
  (e: 'rowClick', row: any): void
  (e: 'inlineUpdate', rowId: string, field: string, value: string): void
}>()

function groupLabel(key: string): string {
  if (!key || key === 'null' || key === 'undefined') return '—'
  if (props.groupByField?.fieldtype === 'Check') return key === '1' || key === 'true' ? 'Так' : 'Ні'
  return key
}

function handleSelectGroup(items: any[]) {
  props.selection.toggleAll(items.map(r => String(r.id)))
}
</script>

<template>
  <div class="flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
    <!-- Shared column header -->
    <DataTable
      :columns="columns"
      :rows="[]"
      :fields="dt?.fields ?? []"
      :is-loading="false"
      :sort-key="sortKey"
      :sort-order="sortOrder"
      :selected-ids="[]"
      :status-config="dt?.status_config"
      :hide-body="true"
      @sort="emit('sort', $event)"
      @select-all="emit('selectAll')"
    />

    <!-- Groups -->
    <div v-for="group in groupedRows" :key="group.key"
      class="rounded-xl border border-border/60 overflow-hidden shadow-sm bg-card hover:shadow-md transition-shadow">
      <!-- Group header -->
      <button type="button"
        class="w-full flex items-center gap-3 px-5 py-3 bg-muted/30 hover:bg-muted/50 transition-colors text-left group"
        @click="emit('toggleGroup', group.key)">
        <div class="size-6 flex items-center justify-center rounded-md bg-background/80 shadow-sm transition-transform duration-300"
          :class="!collapsedGroups.has(group.key) && 'rotate-90'">
          <ChevronRight class="size-4 text-primary" />
        </div>
        <span class="text-sm font-bold text-foreground">{{ groupLabel(group.key) }}</span>
        <div class="ml-auto inline-flex items-center px-2 py-0.5 rounded-full bg-muted text-[10px] font-bold uppercase tracking-wider text-muted-foreground tabular-nums">
          {{ group.items.length }} {{ group.items.length === 1 ? 'запис' : 'записів' }}
        </div>
      </button>

      <!-- Group rows -->
      <Transition name="group">
        <div v-if="!collapsedGroups.has(group.key)" class="border-t border-border/40">
          <DataTable
            :columns="columns"
            :rows="group.items"
            :fields="dt?.fields ?? []"
            :is-loading="false"
            :sort-key="sortKey"
            :sort-order="sortOrder"
            :selected-ids="selection.selectedIds.value"
            :all-selected="selection.allSelected.value"
            :status-config="dt?.status_config"
            :hide-header="true"
            @select="selection.toggle"
            @select-all="handleSelectGroup(group.items)"
            @row-click="emit('rowClick', $event)"
            @inline-update="(rowId, field, value) => emit('inlineUpdate', rowId, field, value)"
          />
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.group-enter-active,
.group-leave-active {
  transition: opacity 300ms ease, max-height 300ms ease;
  overflow: hidden;
}

.group-enter-from,
.group-leave-to {
  opacity: 0;
  max-height: 0;
}

.group-enter-to,
.group-leave-from {
  opacity: 1;
  max-height: 2000px;
}
</style>
