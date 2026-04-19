<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { DocType, ScriptButton, ScriptMenuItem } from '@/types'
import { getExporters } from '@/core/io'
import type { ExportContext } from '@/core/io'
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
  RefreshCw,
} from '@lucide/vue'

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
  (e: 'create-quick'): void
}>()

const { t } = useI18n()
const router = useRouter()

function handleNew() {
  if (!props.isSystemDocType && props.dt?.quick_entry) {
    emit('create-quick')
    return
  }
  const ws = props.workspace ?? 'grunt'
  if (props.isSystemDocType) {
    router.push(`/${ws}/list/DocType/new`)
  } else {
    router.push(props.workspace ? `/${props.workspace}/list/${props.doctype}/new` : `/${props.doctype}/new`)
  }
}
</script>

<template>
  <div class="flex flex-row items-center justify-between gap-4 mb-1 animate-in fade-in slide-in-from-top-2 duration-500 min-h-[40px]">
    <div class="flex items-center gap-3 overflow-hidden">
      <h2 class="text-xl font-bold tracking-tight text-foreground selection:bg-primary/20 truncate">
        {{ dt?.label ?? doctype }}
      </h2>
      <div class="hidden sm:flex items-center">
        <span v-if="meta" class="px-2 py-0.5 rounded-md bg-muted/50 text-[10px] font-bold tracking-wider tabular-nums text-muted-foreground/80 border border-border/40">
          {{ meta.total }}
        </span>
        <span v-else class="w-8 h-4 bg-muted/50 animate-pulse rounded-md"></span>
      </div>
    </div>
    <div class="flex items-center gap-2.5">
      <!-- Refresh button -->
      <Button outlined class="text-foreground transition-all active:scale-95" :title="t('Refresh')"
        @click="emit('refresh')">
        <RefreshCw class="size-4" :class="{ 'animate-spin': isFetching }" />
      </Button>

      <!-- Actions menu -->
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button outlined class="text-foreground hover:bg-muted/80">
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
        :key="btn.label" outlined size="small"
        :severity="btn.severity"
        class="hidden sm:inline-flex shadow-sm"
        @click="btn.action()"
      >
        {{ btn.label }}
      </Button>

      <!-- New button -->
      <Button size="small" class="px-4 shadow-md hover:shadow-lg transition-all active:scale-95 gap-1.5" @click="handleNew" :title="`${t('Add')} (Ctrl+N)`">
        <Plus class="size-4" />
        <span>{{ isSystemDocType ? 'New DocType' : t('Add') }}</span>
      </Button>
    </div>
  </div>
</template>
