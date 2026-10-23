<script setup lang="ts">
/**
 * List page header. The view switcher and the «restrictions» indicator are
 * page chrome; every action - refresh, «Додати», export, the «⋯» menu, script
 * buttons - comes from the list's action registry (core/actions.ts), filled by
 * global_list.js, the DocType's script and ClientScripts. While rows are
 * selected, «Дії ▾» (the `bulk` actions) takes the primary button's place.
 */
import { computed, ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocType } from '@/types'
import { permissionsApi, type ActiveRestriction } from '@/core/api/permissions'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { getRegisteredViews, getViewDef } from '@/core/viewRegistry'
import { ChevronDown, Check, Ban } from '@lucide/vue'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { ActionRegistry } from '@/core/actions'
import type { ListViewProxy } from '@/core/scripting/executor'
import ActionButtons from '@/components/views/actions/ActionButtons.vue'
import ActionMenu from '@/components/views/actions/ActionMenu.vue'
import BulkActionsMenu from '@/components/views/actions/BulkActionsMenu.vue'

const props = defineProps<{
  doctype: string
  dt: DocType | null
  actions: ActionRegistry<ListViewProxy>
  viewMode: string
  selection?: { count: number; total?: number; pageCount?: number }
}>()

const emit = defineEmits<{
  (e: 'update:viewMode', val: string): void
  (e: 'selectAll'): void
  (e: 'clearSelection'): void
}>()

const { t } = useI18n()

const toolbarActions = props.actions.resolved('toolbar')
const primaryActions = props.actions.resolved('primary')
const menuActions = props.actions.resolved('menu')
const bulkActions = props.actions.resolved('bulk')

const hasSelection = computed(() => (props.selection?.count ?? 0) > 0)

// View switcher ("List View ▾" dropdown)

const availableViews = computed(() =>
  getRegisteredViews().filter((def) => {
    if (!def.resolveField) return true
    if (!props.dt) return false
    return def.resolveField(props.dt) !== null
  })
)

const currentView = computed(() => getViewDef(props.viewMode) ?? availableViews.value[0])

// Row-level "Restrictions" (User Permissions)
const restrictions = ref<ActiveRestriction[]>([])
const showRestrictions = ref(false)

async function loadRestrictions() {
  try {
    restrictions.value = await permissionsApi.getRestrictions(props.doctype)
  } catch {
    restrictions.value = []
  }
}
onMounted(loadRestrictions)
watch(() => props.doctype, loadRestrictions)
</script>

<template>
  <div class="flex flex-row items-center justify-end gap-4 animate-in fade-in slide-in-from-top-2 duration-500">
    <div class="flex items-center gap-2.5">
      <div class="flex items-center gap-1">
        <!-- View switcher -->
        <DropdownMenu v-if="availableViews.length > 1">
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm" class="gap-1.5">
              <component :is="currentView?.icon" v-if="currentView" class="size-4" />
              {{ currentView ? t(currentView.label) : '' }}
              <ChevronDown class="size-3.5 opacity-60" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem v-for="def in availableViews" :key="def.type" @click="emit('update:viewMode', def.type)">
              <component :is="def.icon" class="size-4" />
              <span>{{ t(def.label) }}</span>
              <Check v-if="def.type === viewMode" class="ml-auto size-4" />
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <ActionButtons :toolbar="toolbarActions" compact />

        <!-- Restrictions (row-level User Permissions applied to this list) -->
        <Button
          v-if="restrictions.length"
          variant="outline"
          size="icon-sm"
          class="text-amber-600 dark:text-amber-500"
          :title="t('The list is limited by your access rights')"
          @click="showRestrictions = true"
        >
          <Ban class="size-4" />
        </Button>

        <ActionMenu :actions="menuActions" :toolbar="toolbarActions" />
      </div>

      <BulkActionsMenu
        v-if="hasSelection"
        :actions="bulkActions"
        :count="selection!.count"
        :total="selection!.total"
        :page-count="selection!.pageCount"
        @select-all="emit('selectAll')"
        @clear="emit('clearSelection')"
      />
      <ActionButtons v-else :toolbar="[]" :primary="primaryActions" />
    </div>
  </div>

  <Dialog v-model:open="showRestrictions">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Ban class="size-4 text-amber-600 dark:text-amber-500" />
          {{ t('Restrictions') }}
        </DialogTitle>
      </DialogHeader>
      <DialogDescription>
        {{ t('You only see records matching these values.') }}
      </DialogDescription>
      <div class="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ t('Field') }}</TableHead>
              <TableHead>{{ t('Value') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="(r, i) in restrictions" :key="i">
              <TableCell>{{ r.field }}</TableCell>
              <TableCell class="font-medium">{{ r.value }}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </DialogContent>
  </Dialog>
</template>
