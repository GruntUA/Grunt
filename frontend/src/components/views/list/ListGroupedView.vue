<script setup lang="ts">
import { ChevronRight, Layers } from '@lucide/vue'
import type { DocField, DocType } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'
import GruntDataTable from '@/components/views/GruntDataTable.vue'
import { Badge } from '@/components/ui/badge'

interface SelectionState {
  selectedIds: string[]
  allSelected: boolean
  isSelected: (id: string) => boolean
  toggle: (id: string) => void
  toggleAll: (ids: string[]) => void
}

const props = defineProps<{
  dt: DocType | null
  workspace: string
  doctype: string
  groupedRows: GroupedRowBucket[]
  columns: ListColumn[]
  collapsedGroups: Set<string>
  sortKey: string
  sortOrder: 'asc' | 'desc'
  selection?: SelectionState
  groupByField: DocField | null
}>()

const emit = defineEmits<{
  (e: 'toggleGroup', key: string): void
  (e: 'sort', key: string): void
  (e: 'selectAll'): void
  (e: 'rowClick', row: Record<string, unknown>): void
  (e: 'inlineUpdate', rowId: string, field: string, value: string): void
}>()

function groupLabel(key: string): string {
  if (!key || key === 'null' || key === 'undefined') return 'Без значення'
  if (props.groupByField?.fieldtype === 'Check') return key === '1' || key === 'true' ? 'Так' : 'Ні'
  return key
}

function handleSelectGroup(items: Record<string, unknown>[]) {
  props.selection?.toggleAll(items.map((r) => String(r.id ?? r.name ?? '')).filter(Boolean))
}
</script>

<template>
  <div class="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2 duration-700">
    <!-- Shared column header -->
    <div class="bg-card rounded-lg border border-border/60 overflow-hidden">
        <GruntDataTable
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
    </div>

    <!-- Groups -->
    <div class="flex flex-col gap-4">
        <div v-for="group in groupedRows" :key="group.key"
          class="rounded-lg border border-border/40 overflow-hidden bg-card">
          <!-- Group header -->
          <div
            class="w-full flex items-center gap-4 px-6 py-4 bg-muted/20 border-b border-border/5 group cursor-pointer select-none"
            @click="emit('toggleGroup', group.key)">

            <div class="size-9 flex items-center justify-center rounded-lg bg-background border border-border/40 transition-transform duration-300"
              :class="!collapsedGroups.has(group.key) && 'rotate-90'">
              <ChevronRight class="size-5 text-primary" />
            </div>

            <div class="flex flex-col gap-0.5 min-w-0">
                <div class="flex items-center gap-2">
                    <Layers class="size-3.5 text-muted-foreground/40" />
                    <span class="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">{{ groupByField?.label || 'Група' }}</span>
                </div>
                <h3 class="font-semibold text-foreground truncate">{{ groupLabel(group.key) }}</h3>
            </div>

            <div class="ml-auto flex items-center gap-4">
                <div class="flex -space-x-2">
                    <!-- Placeholder for avatars or summary chips if needed -->
                </div>
                <Badge variant="secondary" class="!text-xs !font-semibold !px-3 !py-1 !rounded-full opacity-80">
                  {{ group.items.length }}
                </Badge>
            </div>
          </div>
    
          <!-- Group rows -->
          <Transition name="group-expand">
            <div v-if="!collapsedGroups.has(group.key)" class="bg-card">
              <GruntDataTable
                :columns="columns"
                :rows="group.items"
                :fields="dt?.fields ?? []"
                :row-link-base="`/app/${workspace}/${doctype}`"
                :is-loading="false"
                :sort-key="sortKey"
                :sort-order="sortOrder"
                :selected-ids="selection?.selectedIds || []"
                :all-selected="selection?.allSelected || false"
                :status-config="dt?.status_config"
                :hide-header="true"
                @select="selection?.toggle"
                @select-all="handleSelectGroup(group.items)"
                @row-click="emit('rowClick', $event)"
                @inline-update="(rowId: string, field: string, value: string) => emit('inlineUpdate', rowId, field, value)"
              />
            </div>
          </Transition>
        </div>
    </div>
  </div>
</template>

<style scoped>
.group-expand-enter-active,
.group-expand-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  max-height: 2000px;
  opacity: 1;
}

.group-expand-enter-from,
.group-expand-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-10px);
}
</style>
