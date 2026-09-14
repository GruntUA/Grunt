<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { DocType, ScriptButton, ScriptMenuItem } from '@/types'
import { useAuthStore } from '@/stores/auth'
import { permissionsApi, type ActiveRestriction } from '@/core/api/permissions'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { getExporters } from '@/core/io'
import type { ExportContext } from '@/core/io'
import { getRegisteredViews, getViewDef } from '@/core/viewRegistry'
import {
  Plus,
  MoreHorizontal,
  RefreshCw,
  Download,
  Pencil,
  BarChart2,
  ChevronDown,
  Check,
  Filter,
  Ban,
} from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { ButtonVariants } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

// Client scripts set `severity` as a free-form string; trust it as a Button variant.
function scriptButtonVariant(severity?: string): ButtonVariants['variant'] {
  return (severity as ButtonVariants['variant']) || 'outline'
}

const props = defineProps<{
  doctype: string
  dt: DocType | null
  workspace?: string
  isFetching: boolean
  isSystemDocType: boolean
  showDevActions: boolean
  listButtons: ScriptButton[]
  listMenuItems: ScriptMenuItem[]
  exportCtx: ExportContext | null
  viewMode: string
  /** `listview.can_create` from a client script's `setup_list` — overrides the permission check either way. */
  canCreateOverride?: boolean
}>()

const exporters = getExporters()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'create-quick'): void
  (e: 'update:viewMode', val: string): void
  (e: 'customize-quick-filters'): void
}>()

// ── View switcher ("List View ▾" dropdown) ───────────────────────────────────

const availableViews = computed(() =>
  getRegisteredViews().filter((def) => {
    if (!def.resolveField) return true
    if (!props.dt) return false
    return def.resolveField(props.dt) !== null
  })
)

const currentView = computed(() => getViewDef(props.viewMode) ?? availableViews.value[0])

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

// A DocType with no matching permission row is closed to everyone — same
// rule the backend's RoleAccess applies (no role bypasses permission rows,
// see grunt/permissions/access.py). Mirrors that here so "+ Add" doesn't
// offer an action the server will 405 right back. A client script's
// `listview.can_create = false/true` (setup_list) overrides this either way.
const canCreate = computed(() => {
  if (props.canCreateOverride !== undefined) return props.canCreateOverride
  if (!props.dt) return true // meta still loading — avoid a flash of "no button"
  const perms = props.dt.permissions
  if (!perms || !perms.length) return false // no permission rows = closed to everyone
  const roles = auth.user?.roles ?? []
  return perms.some((p) => p.create && (p.role === 'All' || roles.includes(p.role)))
})

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

const menuItems = computed(() => {
  const items: any[] = []

    // Exporters
    if (!props.isSystemDocType && props.exportCtx) {
        exporters.forEach(exp => {
            items.push({
                label: exp.label,
                icon: Download,
                command: () => exp.export(props.exportCtx!)
            })
        })
        items.push({ separator: true })
    }

    // Dev actions
    if (props.showDevActions) {
        items.push({
            label: t('Edit DocType'),
            icon: Pencil,
            command: () => router.push(`/${props.workspace ?? 'grunt'}/DocType/${props.doctype}`)
        })
        items.push({
            label: t('Customize Quick Filters'),
            icon: Filter,
            command: () => emit('customize-quick-filters')
        })
        items.push({ separator: true })
    }

    // Report builder
    items.push({
        label: t('Create report'),
        icon: BarChart2,
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

// ── Row-level "Restrictions" (User Permissions) ──────────────────────────
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
              {{ currentView?.label }}
              <ChevronDown class="size-3.5 opacity-60" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem v-for="def in availableViews" :key="def.type" @click="emit('update:viewMode', def.type)">
              <component :is="def.icon" class="size-4" />
              <span>{{ def.label }}</span>
              <Check v-if="def.type === viewMode" class="ml-auto size-4" />
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <!-- Refresh button -->
        <Button variant="outline" size="icon-sm" :title="t('Refresh')" @click="emit('refresh')">
          <RefreshCw class="size-4" :class="{ 'animate-spin': isFetching }" />
        </Button>

        <!-- Restrictions (row-level User Permissions applied to this list) -->
        <Button
          v-if="restrictions.length"
          variant="outline"
          size="icon-sm"
          class="text-amber-600 dark:text-amber-500"
          title="Список обмежено вашими правами доступу"
          @click="showRestrictions = true"
        >
          <Ban class="size-4" />
        </Button>

        <!-- Actions menu -->
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="icon-sm">
              <MoreHorizontal class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent class="w-56" align="end">
            <template v-for="(item, idx) in menuItems" :key="idx">
              <DropdownMenuSeparator v-if="item.separator" />
              <DropdownMenuItem v-else @click="item.command?.()">
                <component v-if="item.icon" :is="item.icon" class="size-4" />
                <span>{{ item.label }}</span>
              </DropdownMenuItem>
            </template>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <!-- Custom buttons -->
      <Button
        v-for="btn in listButtons"
        :key="btn.label" size="sm"
        :variant="scriptButtonVariant(btn.severity)"
        class="hidden sm:inline-flex"
        @click="btn.action()"
      >
        {{ btn.label }}
      </Button>

      <!-- New button -->
      <Button v-if="canCreate" size="sm" class="px-4 gap-1.5" @click="handleNew" :title="`${t('Add')} (Ctrl+N)`">
        <Plus class="size-4" />
        <span>{{ isSystemDocType ? 'New DocType' : t('Add') }}</span>
      </Button>
    </div>
  </div>

  <Dialog v-model:open="showRestrictions">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Ban class="size-4 text-amber-600 dark:text-amber-500" />
          Обмеження
        </DialogTitle>
      </DialogHeader>
      <p class="text-muted-foreground -mt-1">
        Ви бачите лише записи, що відповідають цим значенням.
      </p>
      <table class="w-full text-sm border border-border rounded-md overflow-hidden">
        <thead>
          <tr class="bg-muted/50 text-muted-foreground">
            <th class="text-left font-medium px-3 py-2 border-b border-border">Поле</th>
            <th class="text-left font-medium px-3 py-2 border-b border-border">Значення</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in restrictions" :key="i" class="border-b border-border last:border-0">
            <td class="px-3 py-2">{{ r.field }}</td>
            <td class="px-3 py-2 font-medium">{{ r.value }}</td>
          </tr>
        </tbody>
      </table>
    </DialogContent>
  </Dialog>
</template>
