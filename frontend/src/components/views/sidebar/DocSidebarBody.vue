<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  UserPlus,
  Share2,
  Bookmark,
  Printer,
  Check,
  Copy,
  X,
  Tag,
  Plus,
  ChevronRight,
  Loader2,
  CalendarClock,
} from '@lucide/vue'
import type { DocType, GruntDocument, UserPublic } from '@/types'
import type { PresenceUser } from '@/core/composables/usePresence'
import { useDocSidebar } from './useDocSidebar'
import { isAssignmentPlaceholder, type SidebarAssignee } from '@/core/api/docs'
import { useToast } from '@/core/composables/useToast'
import { useDialog } from '@/core/composables/useDialog'
import { formatDate, formatFull, formatRelative } from '@/core/datetime'
import { resolveStatusBadge } from '@/core/status'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
}>()

const router = useRouter()
const toast = useToast()
const dialog = useDialog()
const sb = useDocSidebar(
  () => props.doctype.name,
  () => props.document.name,
)

const imageUrl = computed(() => {
  const field = props.doctype.image_field
  const val = field ? props.document[field] : null
  return typeof val === 'string' && val ? val : null
})
const isBookmarked = computed(() => !!sb.bundle.value.bookmark)

// ── Primary status badge (e.g. "На складі") — moved here from the form toolbar ──
const statusBadge = computed(() => resolveStatusBadge(props.doctype, props.document))

// ── Submission state badge ─────────────────────────────────────────────────────
const docstatusBadge = computed(() => {
  if (!props.doctype.is_submittable) return null
  return (
    [
      { label: 'Чернетка', variant: 'secondary' as const },
      { label: 'Проведено', variant: 'default' as const },
      { label: 'Скасовано', variant: 'destructive' as const },
    ][props.document.docstatus] ?? null
  )
})

// ── Copy id ─────────────────────────────────────────────────────────────────
const copied = ref(false)
async function copyId() {
  try {
    await navigator.clipboard.writeText(props.document.name)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    toast.error('Не вдалося скопіювати')
  }
}

// ── Assign / Share — one dialog, two modes ───────────────────────────────────
const dialogMode = ref<'assign' | 'share' | null>(null)
const pickUser = ref('')
const pickNote = ref('')
const pickPermission = ref<'Read' | 'Write'>('Read')
const matches = ref<UserPublic[]>([])
const saving = ref(false)

function openDialog(mode: 'assign' | 'share') {
  dialogMode.value = mode
  pickUser.value = ''
  pickNote.value = ''
  pickPermission.value = 'Read'
  matches.value = []
}
async function onPickInput() {
  matches.value = await sb.searchUsers(pickUser.value)
}

// A ToDo created without a task text carries an auto-generated placeholder —
// treat that as "no text" so it's not shown as an actual task.
function realNote(a: SidebarAssignee): string {
  const d = (a.description ?? '').trim()
  return isAssignmentPlaceholder(d) ? '' : d
}
// One detail card per assignment (note + state), newest last.
const assigneeTasks = computed(() => sb.bundle.value.assignees)
const STATUS_LABEL: Record<string, string> = { Open: 'Відкрито', 'In Progress': 'В роботі' }
function statusLabel(a: SidebarAssignee): string {
  return a.status ? (STATUS_LABEL[a.status] ?? a.status) : ''
}
function assigneeTooltip(a: SidebarAssignee): string {
  const parts = [sb.personName(a.assigned_to)]
  const note = realNote(a)
  if (note) parts.push(note)
  if (a.created_at) parts.push(`призначено ${formatRelative(a.created_at)}`)
  return parts.join(' — ')
}
const PRIORITY_LABEL: Record<string, string> = { Urgent: 'Терміново', High: 'Високий' }
function priorityTag(a: SidebarAssignee): string {
  return a.priority && a.priority in PRIORITY_LABEL ? PRIORITY_LABEL[a.priority] : ''
}
function openTask(a: SidebarAssignee) {
  router.push(props.workspace ? `/${props.workspace}/ToDo/${a.name}` : `/ToDo/${a.name}`)
}
async function confirmUnassign(a: SidebarAssignee) {
  const ok = await dialog.confirm(`Прибрати ${sb.personName(a.assigned_to)} з відповідальних?`)
  if (ok) await sb.unassign(a.name)
}
async function submitDialog() {
  const user = pickUser.value.trim()
  if (!user) return
  saving.value = true
  try {
    if (dialogMode.value === 'assign') await sb.assign(user, pickNote.value)
    else await sb.share(user, pickPermission.value)
    dialogMode.value = null
  } catch {
    /* silent */
  } finally {
    saving.value = false
  }
}

// ── Tags ────────────────────────────────────────────────────────────────────
const showTagInput = ref(false)
const tagInput = ref('')
const tagAdding = ref(false)
async function submitTag() {
  tagAdding.value = true
  try {
    await sb.addTag(tagInput.value)
    tagInput.value = ''
  } catch {
    /* silent */
  } finally {
    tagAdding.value = false
  }
}

function bookmarkTitle(): string {
  const tf = props.doctype.title_field ?? 'name'
  return String(props.document[tf] ?? props.document.name)
}

function printDoc() {
  const params = new URLSearchParams({
    doctype: props.doctype.name,
    doc_id: props.document.name,
    fmt: 'html',
    autoprint: '1',
  })
  const token = localStorage.getItem('grunt_token')
  if (token) params.set('token', token)
  window.open(`/api/v1/method/grunt.document.base.Document.print?${params.toString()}`, '_blank', 'noopener')
}

function goToLink(l: { source_doctype: string; source_id: string }) {
  const path = props.workspace
    ? `/${props.workspace}/${l.source_doctype}/${l.source_id}`
    : `/${l.source_doctype}/${l.source_id}`
  router.push(path)
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- Image (only when there is one) -->
    <div v-if="imageUrl" class="flex justify-center -mt-1">
      <div class="max-w-full max-h-48 rounded-lg overflow-hidden ring-4 ring-background shadow-sm border border-border/40">
        <img :src="imageUrl" :alt="document.name" class="max-w-full h-auto max-h-48 object-contain" />
      </div>
    </div>

    <!-- Primary status -->
    <div v-if="statusBadge" class="flex items-center gap-2">
      <span class="font-semibold uppercase tracking-wider text-muted-foreground/80">Статус</span>
      <Badge :variant="statusBadge.variant" class="text-xs h-5 px-2">{{ statusBadge.label }}</Badge>
    </div>

    <!-- Identity: id -->
    <div class="flex items-center gap-1.5">
      <code class="font-mono font-semibold text-foreground truncate">{{ document.name }}</code>
      <button
        class="shrink-0 text-muted-foreground/60 hover:text-foreground transition-colors"
        title="Скопіювати ідентифікатор"
        @click="copyId"
      >
        <Check v-if="copied" class="size-3.5 text-success" />
        <Copy v-else class="size-3.5" />
      </button>
      <Badge v-if="docstatusBadge" :variant="docstatusBadge.variant" class="ml-auto text-xs h-5 px-1.5">
        {{ docstatusBadge.label }}
      </Badge>
    </div>

    <!-- Meta: who / when, compact -->
    <div class="flex items-start gap-2.5">
      <Avatar class="!size-7 shrink-0 mt-0.5">
        <AvatarImage v-if="sb.personAvatar(document.owner)" :src="sb.personAvatar(document.owner)!" />
        <AvatarFallback class="!text-[10px] !bg-primary/10 !text-primary">
          {{ sb.personInitials(document.owner) }}
        </AvatarFallback>
      </Avatar>
      <div class="flex flex-col gap-0.5 min-w-0 leading-snug">
        <span class="truncate" :title="`${document.owner} · ${formatFull(document.created_at)}`">
          <span class="font-semibold text-foreground">{{ sb.personName(document.owner) }}</span>
          <span class="text-muted-foreground"> · створив {{ formatRelative(document.created_at) }}</span>
        </span>
        <span
          class="truncate"
          :title="`${document.modified_by || document.owner} · ${formatFull(document.modified_at)}`"
        >
          <span class="font-semibold text-foreground">{{ sb.personName(document.modified_by || document.owner) }}</span>
          <span class="text-muted-foreground"> · змінив {{ formatRelative(document.modified_at) }}</span>
        </span>
      </div>
    </div>

    <!-- People: assignees + access -->
    <div class="flex flex-col gap-3 p-3 bg-muted/30 rounded-lg border border-border/40">
      <div class="flex items-center justify-between">
        <span class="font-semibold uppercase tracking-wider text-muted-foreground/80">Люди</span>
        <div class="flex items-center gap-0.5">
          <Button variant="ghost" size="icon" class="size-6" title="Призначити відповідального" @click="openDialog('assign')">
            <UserPlus class="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon" class="size-6" title="Поділитися документом" @click="openDialog('share')">
            <Share2 class="size-3.5" />
          </Button>
        </div>
      </div>

      <!-- Assignees -->
      <div class="flex flex-col gap-2">
        <div class="flex items-center gap-2">
          <span class="text-muted-foreground shrink-0">Відповідальні</span>
          <div v-if="sb.bundle.value.assignees.length" class="flex flex-wrap gap-1.5">
            <div
              v-for="a in sb.bundle.value.assignees"
              :key="a.name"
              class="relative group"
              :title="assigneeTooltip(a)"
            >
              <button type="button" @click="openTask(a)">
                <Avatar
                  class="!size-7 border transition-shadow hover:ring-2 hover:ring-primary/30"
                  :class="a.is_overdue
                    ? 'border-destructive/60 ring-1 ring-destructive/40'
                    : a.status === 'In Progress' ? 'border-primary/60 ring-1 ring-primary/40' : 'border-border/60'"
                >
                  <AvatarImage v-if="sb.personAvatar(a.assigned_to)" :src="sb.personAvatar(a.assigned_to)!" />
                  <AvatarFallback class="!text-[10px]">{{ sb.personInitials(a.assigned_to) }}</AvatarFallback>
                </Avatar>
              </button>
              <button
                class="absolute -top-1 -right-1 size-3.5 rounded-full bg-background border border-border shadow-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                :title="`Прибрати ${sb.personName(a.assigned_to)}`"
                @click="confirmUnassign(a)"
              >
                <X class="size-2.5 text-destructive" />
              </button>
            </div>
          </div>
          <span v-else class="text-muted-foreground/50">нема</span>
        </div>

        <ul v-if="assigneeTasks.length" class="flex flex-col gap-1.5">
          <li v-for="a in assigneeTasks" :key="a.name">
            <button
              type="button"
              class="w-full text-left flex flex-col gap-1 rounded-lg border border-border/40 bg-background px-2 py-1.5 shadow-sm hover:border-primary/50 hover:bg-primary/5 transition-colors"
              @click="openTask(a)"
            >
              <span v-if="realNote(a)" class="leading-snug text-foreground/80 line-clamp-2">
                {{ realNote(a) }}
              </span>
              <span class="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                <Badge
                  :variant="a.status === 'In Progress' ? 'secondary' : 'outline'"
                  class="!text-[10px] !py-0 !px-1.5 !font-normal"
                >
                  {{ statusLabel(a) }}
                </Badge>
                <Badge
                  v-if="a.due_date"
                  :variant="a.is_overdue ? 'destructive' : 'outline'"
                  class="!text-[10px] !py-0 !px-1.5 !font-normal gap-0.5"
                >
                  <CalendarClock class="size-2.5" />
                  {{ formatDate(a.due_date) }}
                </Badge>
                <Badge v-if="priorityTag(a)" variant="outline" class="!text-[10px] !py-0 !px-1.5 !font-normal">
                  {{ priorityTag(a) }}
                </Badge>
                <span class="ml-auto shrink-0">{{ sb.personName(a.assigned_to) }}</span>
              </span>
            </button>
          </li>
        </ul>
      </div>

      <!-- Access (collapsed by default) -->
      <Collapsible v-if="sb.bundle.value.shares.length" class="flex flex-col gap-2">
        <CollapsibleTrigger
          class="group flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronRight class="size-3 transition-transform group-data-[state=open]:rotate-90" />
          Доступ · {{ sb.bundle.value.shares.length }}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div class="flex flex-col gap-1.5 pt-0.5">
            <div
              v-for="s in sb.bundle.value.shares"
              :key="s.name"
              class="flex items-center gap-2 group"
            >
              <Avatar class="!size-5 shrink-0">
                <AvatarImage v-if="sb.personAvatar(s.user)" :src="sb.personAvatar(s.user)!" />
                <AvatarFallback class="!text-[9px]">{{ sb.personInitials(s.user) }}</AvatarFallback>
              </Avatar>
              <span class="truncate flex-1">{{ sb.personName(s.user) }}</span>
              <span class="uppercase tracking-tighter text-muted-foreground/60">{{ s.permission }}</span>
              <X
                class="size-3 cursor-pointer text-muted-foreground/40 hover:text-destructive transition-colors"
                @click="sb.unshare(s.name)"
              />
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>

    <!-- Tags -->
    <div class="flex flex-col gap-2.5 p-3 bg-muted/30 rounded-lg border border-border/40">
      <div class="flex items-center justify-between">
        <span class="font-semibold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
          <Tag class="size-3" />
          Теги
        </span>
        <Button variant="ghost" size="icon" class="size-6" title="Додати тег" @click="showTagInput = !showTagInput">
          <Plus class="size-3.5 transition-transform" :class="{ 'rotate-45': showTagInput }" />
        </Button>
      </div>

      <div v-if="sb.bundle.value.tags.length" class="flex flex-wrap gap-1.5">
        <Badge
          v-for="t in sb.bundle.value.tags"
          :key="t.name"
          class="px-2 py-0.5 text-xs font-semibold bg-background border border-border/60 shadow-sm"
        >
          <span class="mr-1.5">{{ t.tag }}</span>
          <X
            class="size-3 cursor-pointer hover:text-destructive transition-colors shrink-0"
            @click="sb.removeTag(t.name)"
          />
        </Badge>
      </div>
      <span v-else-if="!showTagInput" class="text-muted-foreground/50">нема тегів</span>

      <div v-if="showTagInput" class="inline-flex h-8 shadow-sm w-full">
        <Input
          v-model="tagInput"
          placeholder="Назва тега..."
          autofocus
          class="!text-xs h-full rounded-r-none flex-1"
          @keydown.enter.prevent="submitTag"
        />
        <Button
          class="h-full px-2 rounded-l-none border-l-0"
          :disabled="!tagInput.trim() || tagAdding"
          @click="submitTag"
        >
          <Loader2 v-if="tagAdding" class="size-3.5 animate-spin" />
          <Plus v-else class="size-3.5" />
        </Button>
      </div>
    </div>

    <!-- Backlinks: counter only, expandable -->
    <Collapsible
      v-if="sb.bundle.value.backlinks.length"
      class="flex flex-col gap-2 p-3 bg-muted/30 rounded-lg border border-border/40"
    >
      <CollapsibleTrigger
        class="group flex items-center gap-1.5 font-semibold uppercase tracking-wider text-muted-foreground/80 hover:text-foreground transition-colors"
      >
        <ChevronRight class="size-3 transition-transform group-data-[state=open]:rotate-90" />
        Зв'язки · {{ sb.bundle.value.backlinks.length }}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div class="flex flex-col gap-1.5 pt-0.5">
          <button
            v-for="l in sb.bundle.value.backlinks"
            :key="`${l.source_doctype}-${l.source_id}`"
            class="flex items-center gap-2 p-2 rounded-lg bg-background border border-border/40 hover:border-primary/50 hover:bg-primary/5 transition-colors group text-left shadow-sm"
            @click="goToLink(l)"
          >
            <ChevronRight class="size-3 text-muted-foreground/50 group-hover:text-primary transition-colors" />
            <div class="flex flex-col min-w-0">
              <span class="font-semibold text-foreground truncate">{{ l.source_doctype }}</span>
              <span class="text-muted-foreground truncate">{{ l.source_id }}</span>
            </div>
          </button>
        </div>
      </CollapsibleContent>
    </Collapsible>

    <!-- Bottom actions -->
    <div class="flex gap-2">
      <Button
        variant="outline"
        size="sm"
        :class="['flex-1 shadow-sm', isBookmarked ? 'text-warning border-warning/40' : 'text-foreground']"
        @click="sb.toggleBookmark(bookmarkTitle())"
      >
        <Bookmark class="size-3.5 mr-2" :fill="isBookmarked ? 'currentColor' : 'none'" />
        <span class="font-semibold">{{ isBookmarked ? 'У закладках' : 'Закладка' }}</span>
      </Button>
      <Button variant="outline" size="sm" class="flex-1 text-foreground shadow-sm" @click="printDoc">
        <Printer class="size-3.5 mr-2" />
        <span class="font-semibold">Друк</span>
      </Button>
    </div>

    <!-- Assign / Share dialog -->
    <Dialog :open="dialogMode !== null" @update:open="(v) => { if (!v) dialogMode = null }">
      <DialogContent class="max-w-sm w-full mx-4 p-0 px-6 pb-6 pt-1">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2 font-semibold text-lg">
            <component :is="dialogMode === 'assign' ? UserPlus : Share2" class="size-5 text-primary" />
            {{ dialogMode === 'assign' ? 'Призначити відповідального' : 'Поділитися документом' }}
          </DialogTitle>
        </DialogHeader>

        <div class="flex flex-col gap-5 py-2">
          <div class="flex flex-col gap-2">
            <label class="font-semibold uppercase tracking-wider text-muted-foreground">Email або логін</label>
            <Input v-model="pickUser" placeholder="Пошук користувача..." class="w-full" @input="onPickInput" />
            <div
              v-if="matches.length"
              class="border border-border rounded-md overflow-hidden max-h-40 overflow-y-auto divide-y divide-border/60"
            >
              <button
                v-for="u in matches"
                :key="u.email"
                type="button"
                class="w-full px-3 py-2 text-left hover:bg-primary/5 transition-colors flex items-center gap-2"
                @click="pickUser = u.email; matches = []"
              >
                <Avatar class="!size-6"><AvatarFallback class="!text-[10px]">{{ (u.full_name || u.email).slice(0, 2).toUpperCase() }}</AvatarFallback></Avatar>
                <div class="flex flex-col min-w-0">
                  <span class="font-medium truncate">{{ u.full_name || u.email }}</span>
                  <span class="text-muted-foreground truncate">{{ u.email }}</span>
                </div>
              </button>
            </div>
          </div>

          <div v-if="dialogMode === 'assign'" class="flex flex-col gap-2">
            <label class="font-semibold uppercase tracking-wider text-muted-foreground">Текст задачі</label>
            <Textarea
              v-model="pickNote"
              rows="3"
              placeholder="Що потрібно зробити? Напр. «Роутер передати на склад або списати»"
              class="w-full resize-none"
            />
          </div>

          <div v-if="dialogMode === 'share'" class="flex flex-col gap-2">
            <label class="font-semibold uppercase tracking-wider text-muted-foreground">Рівень доступу</label>
            <Select v-model="pickPermission">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="Read">Читання</SelectItem>
                <SelectItem value="Write">Редагування</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <div class="flex gap-2 w-full pt-2">
            <Button variant="outline" class="flex-1" @click="dialogMode = null">Скасувати</Button>
            <Button class="flex-1" :disabled="!pickUser.trim() || saving" @click="submitDialog">
              <Loader2 v-if="saving" class="size-4 animate-spin mr-2" />
              <span v-else>{{ dialogMode === 'assign' ? 'Призначити' : 'Надати доступ' }}</span>
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
