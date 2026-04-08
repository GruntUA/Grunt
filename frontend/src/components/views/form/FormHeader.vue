<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Loader2,
  ChevronRight,
  Printer,
  FileSpreadsheet,
  FileText,
  Globe,
  Trash2,
  ChevronDown,
  History,
  Copy,
  Undo2,
  EllipsisVertical,
  ExternalLink,
  Settings2,
  RefreshCw,
} from 'lucide-vue-next'
import WorkflowBar from '@/components/views/WorkflowBar.vue'

const props = defineProps<{
  dt: DocType | null
  doctype: string
  id: string | null
  workspace?: string
  docTitle: string
  document: any
  isDirty: boolean
  isLoading: boolean
  isSaving: boolean
  scriptButtons: any[]
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'delete'): void
  (e: 'duplicate'): void
  (e: 'toggleLog'): void
  (e: 'invalidate'): void
}>()

const auth = useAuthStore()
const router = useRouter()
const queryClient = useQueryClient()

function handleRefresh() {
  if (props.id) {
    queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
    emit('invalidate')
  }
}

function handleUndo() {
  router.go(0)
}
</script>

<template>
  <div class="bg-card rounded-xl shadow-md ring-1 ring-border/60 mb-6 font-primary transition-all duration-300">
    <!-- Top bar: breadcrumb + actions -->
    <div class="flex items-center justify-between gap-4 px-6 pt-5 pb-4">
      <div class="min-w-0">
        <nav class="flex items-center gap-1.5 text-sm mb-1">
          <button class="text-muted-foreground hover:text-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded px-1"
            @click="router.push(workspace ? `/${workspace}/list/${doctype}` : `/${doctype}`)">
            {{ dt?.label ?? doctype }}
          </button>
          <ChevronRight class="size-3.5 text-muted-foreground/40" />
        </nav>
        <div class="flex items-center gap-3">
          <h1 class="text-2xl font-bold text-foreground truncate selection:bg-primary/20">{{ docTitle }}</h1>
          <Badge v-if="isDirty" variant="outline" class="border-amber-400 bg-amber-50/50 text-amber-600 animate-in fade-in slide-in-from-left-2 duration-300">
            Не збережено
          </Badge>
        </div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <!-- Client script buttons -->
        <Button v-for="btn in scriptButtons" :key="btn.label" :variant="(btn.variant as any) ?? 'outline'" size="sm"
          @click="btn.action" class="hidden sm:inline-flex">
          {{ btn.label }}
        </Button>

        <Button v-if="id" variant="outline" size="sm" class="w-9 p-0 text-foreground" title="Оновити"
          :disabled="isDirty || isLoading"
          @click="handleRefresh">
          <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" />
        </Button>

        <Button :disabled="isSaving" size="sm" @click="emit('save')" class="shadow-sm hover:shadow-md transition-shadow">
          <Loader2 v-if="isSaving" class="size-4 animate-spin mr-1.5" />
          Зберегти
        </Button>

        <!-- Context menu -->
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="icon-sm" class="text-foreground hover:bg-muted/80">
              <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-52 p-1.5 selection:bg-primary/10">
            <!-- Print submenu -->
            <DropdownMenuSub v-if="id">
              <DropdownMenuSubTrigger class="gap-2">
                <Printer class="size-4 text-muted-foreground" />
                <span>Друкувати</span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent class="p-1.5">
                <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=xlsx&token=${auth.token}`" class="gap-2">
                  <FileSpreadsheet class="size-4 text-emerald-500" />
                  <span>Excel (.xlsx)</span>
                </DropdownMenuItem>
                <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=pdf&token=${auth.token}`" class="gap-2">
                  <FileText class="size-4 text-rose-500" />
                  <span>PDF</span>
                </DropdownMenuItem>
                <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=html&token=${auth.token}`"
                  target="_blank" class="gap-2">
                  <Globe class="size-4 text-sky-500" />
                  <span>HTML</span>
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>

            <DropdownMenuItem v-if="id" as="a" :href="`/${props.workspace ?? ''}/list/${doctype}/${id}`"
              target="_blank" class="gap-2">
              <ExternalLink class="size-4 text-muted-foreground" />
              <span>Відкрити у новій вкладці</span>
            </DropdownMenuItem>

            <DropdownMenuItem as="a" :href="`/${props.workspace ?? ''}/list/DocType/${doctype}`" target="_blank" class="gap-2">
              <Settings2 class="size-4 text-muted-foreground" />
              <span>Редагувати Доктайп</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="dt" as="a"
              :href="`/${props.workspace ?? 'grunt'}/list/PrintFormat?filter[doctype]=${doctype}`" target="_blank" class="gap-2">
              <Printer class="size-4 text-muted-foreground" />
              <span>Налаштувати друк</span>
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuItem v-if="id" @click="emit('duplicate')" class="gap-2">
              <Copy class="size-4 text-muted-foreground" />
              <span>Створити копію</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="id && isDirty" @click="handleUndo" class="gap-2">
              <Undo2 class="size-4 text-muted-foreground" />
              <span>Скасувати зміни</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="id" @click="emit('toggleLog')" class="gap-2">
              <History class="size-4 text-muted-foreground" />
              <span>Журнал активності</span>
            </DropdownMenuItem>

            <template v-if="id">
              <DropdownMenuSeparator />
              <DropdownMenuItem class="text-destructive focus:text-destructive focus:bg-destructive/10 gap-2" @click="emit('delete')">
                <Trash2 class="size-4" />
                <span>Видалити</span>
              </DropdownMenuItem>
            </template>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>

    <!-- Workflow (inside the header card) -->
    <WorkflowBar v-if="!isLoading && dt && id && document && dt.workflow" :doctype="dt" :doc-id="id"
      :doc="document as Record<string, unknown>"
      @transitioned="handleRefresh" />
  </div>
</template>
