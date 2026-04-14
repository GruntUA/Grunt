<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { DocType, ScriptButton, ScriptMenuItem } from '@/types'
import { getExporters } from '@/core/io'
import type { ExportContext } from '@/core/io'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Download,
  Plus,
  MoreHorizontal,
  Pencil,
  FileBarChart,
  RefreshCw,
} from 'lucide-vue-next'

const props = defineProps<{
  doctype: string
  dt: DocType | null
  workspace?: string
  meta?: { total: number }
  isFetching: boolean
  isSystemDocType: boolean
  showDevActions: boolean
  listButtons: ScriptButton[]
  listMenuItems: ScriptMenuItem[]
  exportCtx: ExportContext | null
}>()

const exporters = getExporters()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const { t } = useI18n()
const router = useRouter()

function handleNew() {
  const ws = props.workspace ?? 'grunt'
  if (props.isSystemDocType) {
    router.push(`/${ws}/list/DocType/new`)
  } else {
    router.push(props.workspace ? `/${props.workspace}/list/${props.doctype}/new` : `/${props.doctype}/new`)
  }
}
</script>

<template>
  <div class="flex flex-wrap items-end justify-between gap-4 mb-2 animate-in fade-in slide-in-from-top-2 duration-500">
    <div class="space-y-1">
      <h2 class="text-3xl font-extrabold tracking-tight text-foreground selection:bg-primary/20">
        {{ dt?.label ?? doctype }}
      </h2>
      <p class="text-muted-foreground font-medium text-sm flex items-center gap-2">
        <span v-if="meta" class="px-2 py-0.5 rounded-full bg-muted text-[11px] uppercase tracking-wider tabular-nums">
          {{ meta.total }} {{ meta.total === 1 ? 'запис' : 'записів' }}
        </span>
        <span v-else class="w-16 h-4 bg-muted animate-pulse rounded"></span>
      </p>
    </div>
    <div class="flex items-center gap-2.5">
      <!-- Refresh button -->
      <Button variant="outline" size="sm" class="h-9 w-9 p-0 text-foreground transition-all active:scale-95" :title="t('Refresh')"
        @click="emit('refresh')">
        <RefreshCw class="size-4" :class="{ 'animate-spin': isFetching }" />
      </Button>

      <!-- Actions menu -->
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" class="text-foreground h-9 w-9 p-0 hover:bg-muted/80">
            <MoreHorizontal class="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-56 p-1.5">
          <!-- Dynamic exporters -->
          <template v-if="!isSystemDocType && exportCtx">
            <DropdownMenuItem
              v-for="exp in exporters"
              :key="exp.id"
              class="gap-2"
              @click="exp.export(exportCtx!)"
            >
              <Download class="size-4 text-muted-foreground" />
              <span>{{ exp.label }}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </template>

          <!-- Dev actions -->
          <template v-if="showDevActions">
            <DropdownMenuItem class="gap-2" @click="router.push(`/${workspace ?? 'grunt'}/list/DocType/${doctype}`)">
              <Pencil class="size-4 text-muted-foreground" />
              <span>{{ t('Edit DocType') }}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </template>

          <!-- Report builder -->
          <DropdownMenuItem class="gap-2"
            @click="router.push({ name: 'report-builder', params: { workspaceName: workspace ?? 'grunt' }, query: { doctype: doctype } })">
            <FileBarChart class="size-4 text-muted-foreground" />
            <span>{{ t('Create report') }}</span>
          </DropdownMenuItem>

          <!-- Script menu items -->
          <template v-if="listMenuItems.length">
            <template v-for="item in listMenuItems" :key="item.label">
              <DropdownMenuSeparator v-if="item.separator_before" />
              <DropdownMenuItem class="gap-2" @click="item.action()">
                <span>{{ item.label }}</span>
              </DropdownMenuItem>
            </template>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>

      <!-- Custom buttons -->
      <Button
        v-for="btn in listButtons"
        :key="btn.label"
        :variant="(btn.variant as any) || 'outline'"
        size="sm"
        class="hidden sm:inline-flex h-9 shadow-sm"
        @click="btn.action()"
      >
        {{ btn.label }}
      </Button>

      <!-- New button -->
      <Button size="sm" class="h-9 px-4 shadow-md hover:shadow-lg transition-all active:scale-95 gap-1.5" @click="handleNew">
        <Plus class="size-4" />
        <span>{{ isSystemDocType ? 'New DocType' : t('Add') }}</span>
      </Button>
    </div>
  </div>
</template>
