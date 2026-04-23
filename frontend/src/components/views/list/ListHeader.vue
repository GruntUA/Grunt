<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { DocType, ScriptButton, ScriptMenuItem } from '@/types'
import { getExporters } from '@/core/io'
import type { ExportContext } from '@/core/io'
import type { MenuItem } from 'primevue/menuitem'
import {
  Plus,
  MoreHorizontal,
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
    router.push(`/${ws}/DocType/new`)
  } else {
    router.push(props.workspace ? `/${props.workspace}/${props.doctype}/new` : `/${props.doctype}/new`)
  }
}

// PrimeVue Menu
const menu = ref()
const toggleMenu = (event: Event) => {
    menu.value.toggle(event)
}

const menuItems = computed(() => {
  const items: MenuItem[] = []

    // Exporters
    if (!props.isSystemDocType && props.exportCtx) {
        exporters.forEach(exp => {
            items.push({
                label: exp.label,
                icon: 'pi pi-download',
                command: () => exp.export(props.exportCtx!)
            })
        })
        items.push({ separator: true })
    }

    // Dev actions
    if (props.showDevActions) {
        items.push({
            label: t('Edit DocType'),
            icon: 'pi pi-pencil',
            command: () => router.push(`/${props.workspace ?? 'grunt'}/DocType/${props.doctype}`)
        })
        items.push({ separator: true })
    }

    // Report builder
    items.push({
        label: t('Create report'),
        icon: 'pi pi-chart-bar',
        command: () => router.push({ 
            name: 'report-builder', 
            params: { workspaceName: props.workspace ?? 'grunt' }, 
            query: { doctype: props.doctype } 
        })
    })

    // Script menu items
    if (props.listMenuItems.length) {
        props.listMenuItems.forEach(item => {
            if (item.separator_before) items.push({ separator: true })
            items.push({
                label: item.label,
                command: () => item.action()
            })
        })
    }

    return items
})
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
      <Button outlined class="text-foreground transition-all active:scale-95 shadow-sm" :title="t('Refresh')"
        @click="emit('refresh')">
        <RefreshCw class="size-4" :class="{ 'animate-spin': isFetching }" />
      </Button>

      <!-- Actions menu -->
      <Button outlined class="text-foreground hover:bg-muted/80 shadow-sm" @click="toggleMenu">
        <MoreHorizontal class="size-4" />
      </Button>
      <Menu ref="menu" :model="menuItems" :popup="true" class="w-56" />

      <!-- Custom buttons -->
      <Button
        v-for="btn in listButtons"
        :key="btn.label" outlined size="small"
        :severity="btn.severity"
        class="hidden sm:inline-flex shadow-sm hover:shadow-md transition-all active:scale-95"
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
