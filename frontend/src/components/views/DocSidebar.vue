<script setup lang="ts">
import { ref, computed, onMounted, useAttrs } from 'vue'
import type { DocType, GruntDocument } from '@/types'
import { docsApi, type BacklinkItem, type TimelineItem } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import type { GruntUserPublic } from '@/types'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  UserPlus,
  Share2,
  Link as LinkIcon,
  Clock,
  User,
  ChevronRight,
  ImageIcon,
  Plus,
  X,
  Loader2,
  Tag,
  Bookmark,
  MessageSquare,
  Activity,
  Send,
  Trash2,
} from 'lucide-vue-next'
import PresenceAvatars from '@/components/ui/PresenceAvatars.vue'
import type { PresenceUser } from '@/core/composables/usePresence'
import { useRouter } from 'vue-router'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
}>()

const router = useRouter()
const attrs = useAttrs()
const auth = useAuthStore()

defineOptions({ inheritAttrs: false })

// ── Tabs ──────────────────────────────────────────────────────────────────────

const activeTab = ref<'details' | 'timeline'>('details')

// ── Image ────────────────────────────────────────────────────────────────────

const imageUrl = computed(() => {
  if (!props.doctype.image_field) return null
  const val = props.document[props.doctype.image_field]
  return typeof val === 'string' && val ? val : null
})

// ── Meta info ─────────────────────────────────────────────────────────────────

const createdAt = computed(() => {
  const d = props.document.created_at
  return d ? new Date(d).toLocaleString('uk-UA') : '—'
})

const modifiedAt = computed(() => {
  const d = props.document.modified_at
  return d ? new Date(d).toLocaleString('uk-UA') : '—'
})

// ── Bookmark ──────────────────────────────────────────────────────────────────

const bookmark = ref<GruntDocument | null>(null)
const bookmarkLoading = ref(false)

async function loadBookmark() {
  try {
    bookmark.value = await docsApi.getBookmark(props.doctype.name, props.document.id)
  } catch { /* silent */ }
}

async function toggleBookmark() {
  bookmarkLoading.value = true
  try {
    if (bookmark.value) {
      await docsApi.removeBookmark(props.doctype.name, props.document.id)
      bookmark.value = null
    } else {
      const title = String(props.document[props.doctype.title_field ?? 'name'] ?? props.document.id)
      bookmark.value = await docsApi.addBookmark(props.doctype.name, props.document.id, title)
    }
  } catch { /* silent */ }
  finally { bookmarkLoading.value = false }
}

// ── Assignees ─────────────────────────────────────────────────────────────────

const assignees = ref<GruntDocument[]>([])
const assignLoading = ref(false)

async function loadAssignees() {
  assignLoading.value = true
  try {
    assignees.value = await docsApi.getAssignees(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { assignLoading.value = false }
}

const showAssignDialog = ref(false)
const assignUser = ref('')
const assignSaving = ref(false)

async function submitAssign() {
  const user = assignUser.value.trim()
  if (!user) return
  assignSaving.value = true
  try {
    await docsApi.assign(props.doctype.name, props.document.id, user)
    await loadAssignees()
    showAssignDialog.value = false
    assignUser.value = ''
  } catch { /* silent */ }
  finally { assignSaving.value = false }
}

async function removeAssignee(assignee: GruntDocument) {
  try {
    await docsApi.unassign(assignee.id)
    assignees.value = assignees.value.filter(a => a.id !== assignee.id)
  } catch { /* silent */ }
}

// ── Shared with ───────────────────────────────────────────────────────────────

const sharedWith = ref<GruntDocument[]>([])
const shareLoading = ref(false)

async function loadShared() {
  shareLoading.value = true
  try {
    sharedWith.value = await docsApi.getSharedWith(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { shareLoading.value = false }
}

const showShareDialog = ref(false)
const shareUser = ref('')
const sharePermission = ref<'Read' | 'Write'>('Read')
const shareSaving = ref(false)

async function submitShare() {
  const user = shareUser.value.trim()
  if (!user) return
  shareSaving.value = true
  try {
    await docsApi.share(props.doctype.name, props.document.id, user, sharePermission.value)
    await loadShared()
    showShareDialog.value = false
    shareUser.value = ''
    sharePermission.value = 'Read'
  } catch { /* silent */ }
  finally { shareSaving.value = false }
}

async function removeShare(share: GruntDocument) {
  try {
    await docsApi.unshare(share.id)
    sharedWith.value = sharedWith.value.filter(s => s.id !== share.id)
  } catch { /* silent */ }
}

// ── Tags ──────────────────────────────────────────────────────────────────────

const tags = ref<GruntDocument[]>([])
const tagsLoading = ref(false)
const tagInput = ref('')
const tagAdding = ref(false)

async function loadTags() {
  tagsLoading.value = true
  try {
    tags.value = await docsApi.getTags(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { tagsLoading.value = false }
}

async function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (tags.value.some(t => (t.tag as string)?.toLowerCase() === tag.toLowerCase())) {
    tagInput.value = ''
    return
  }
  tagAdding.value = true
  try {
    const created = await docsApi.addTag(props.doctype.name, props.document.id, tag)
    tags.value = [...tags.value, created]
    tagInput.value = ''
  } catch { /* silent */ }
  finally { tagAdding.value = false }
}

async function removeTag(tag: GruntDocument) {
  try {
    await docsApi.removeTag(tag.id)
    tags.value = tags.value.filter(t => t.id !== tag.id)
  } catch { /* silent */ }
}

function onTagKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    addTag()
  }
}

// ── Backlinks ─────────────────────────────────────────────────────────────────

const links = ref<BacklinkItem[]>([])
const linksLoading = ref(false)

async function loadLinks() {
  linksLoading.value = true
  try {
    links.value = await docsApi.getLinks(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { linksLoading.value = false }
}

function navigateToLink(link: BacklinkItem) {
  const path = props.workspace
    ? `/${props.workspace}/list/${link.source_doctype}/${link.source_id}`
    : `/${link.source_doctype}/${link.source_id}`
  router.push(path)
}

// ── Timeline ──────────────────────────────────────────────────────────────────

const timeline = ref<TimelineItem[]>([])
const timelineLoading = ref(false)

async function loadTimeline() {
  timelineLoading.value = true
  try {
    timeline.value = await docsApi.getTimeline(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { timelineLoading.value = false }
}

function timelineLabel(item: TimelineItem): string {
  if (item.type === 'comment') return item.content ?? ''
  const labels: Record<string, string> = {
    create: 'Створив документ',
    update: 'Оновив документ',
    delete: 'Видалив документ',
    bulk_update: 'Масове оновлення',
    restore: 'Відновив версію',
    transition: 'Змінив статус',
  }
  return labels[item.action ?? ''] ?? item.action ?? ''
}

function fmtDate(d: string | null) {
  return d ? new Date(d).toLocaleString('uk-UA') : ''
}

// ── Comments ──────────────────────────────────────────────────────────────────

const commentInput = ref('')
const commentSending = ref(false)

async function sendComment() {
  const text = commentInput.value.trim()
  if (!text) return
  commentSending.value = true
  try {
    await docsApi.addComment(props.doctype.name, props.document.id, text)
    commentInput.value = ''
    await loadTimeline()
  } catch { /* silent */ }
  finally { commentSending.value = false }
}

async function deleteComment(item: TimelineItem) {
  try {
    await docsApi.deleteComment(props.doctype.name, props.document.id, item.id)
    timeline.value = timeline.value.filter(t => t.id !== item.id)
  } catch { /* silent */ }
}

function onCommentKeydown(e: KeyboardEvent) {
  if (mentionDropdown.value.length && e.key === 'ArrowDown') {
    e.preventDefault()
    mentionIndex.value = (mentionIndex.value + 1) % mentionDropdown.value.length
    return
  }
  if (mentionDropdown.value.length && e.key === 'ArrowUp') {
    e.preventDefault()
    mentionIndex.value = (mentionIndex.value - 1 + mentionDropdown.value.length) % mentionDropdown.value.length
    return
  }
  if (mentionDropdown.value.length && e.key === 'Enter') {
    e.preventDefault()
    insertMention(mentionDropdown.value[mentionIndex.value])
    return
  }
  if (mentionDropdown.value.length && e.key === 'Escape') {
    mentionDropdown.value = []
    return
  }
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    sendComment()
  }
}

// ── @mention autocomplete ─────────────────────────────────────────────────────

const allUsers = ref<GruntUserPublic[]>([])
const mentionDropdown = ref<GruntUserPublic[]>([])
const mentionIndex = ref(0)
const mentionQuery = ref('')

async function ensureUsers() {
  if (allUsers.value.length) return
  try { allUsers.value = await authAdminApi.listUsers() } catch { /* silent */ }
}

function onCommentInput(e: Event) {
  const ta = e.target as HTMLTextAreaElement
  const val = ta.value
  const pos = ta.selectionStart ?? val.length
  const before = val.slice(0, pos)
  const match = before.match(/@([\w.+\-]*)$/)
  if (match) {
    mentionQuery.value = match[1].toLowerCase()
    ensureUsers().then(() => {
      mentionDropdown.value = allUsers.value
        .filter(u =>
          u.email.toLowerCase().includes(mentionQuery.value) ||
          u.full_name.toLowerCase().includes(mentionQuery.value)
        )
        .slice(0, 6)
      mentionIndex.value = 0
    })
  } else {
    mentionDropdown.value = []
  }
}

function insertMention(user: GruntUserPublic) {
  const before = commentInput.value
  const pos = before.lastIndexOf('@' + mentionQuery.value)
  commentInput.value = before.slice(0, pos) + `@${user.email} ` + before.slice(pos + 1 + mentionQuery.value.length)
  mentionDropdown.value = []
}

// ── Mount ─────────────────────────────────────────────────────────────────────

onMounted(() => {
  loadAssignees()
  loadShared()
  loadTags()
  loadLinks()
  loadBookmark()
  loadTimeline()
})
</script>

<template>
  <aside v-bind="attrs" class="flex flex-col gap-0 w-full">
    <!-- Tab nav -->
    <div class="flex border-b border-border mb-4 -mx-0">
      <button
        class="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition-colors"
        :class="activeTab === 'details' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'details'"
      >
        <User class="size-3.5" />
        Деталі
      </button>
      <button
        class="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition-colors"
        :class="activeTab === 'timeline' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'timeline'"
      >
        <Activity class="size-3.5" />
        Активність
        <span v-if="timeline.filter(t => t.type === 'comment').length > 0"
          class="ml-0.5 px-1.5 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-bold">
          {{ timeline.filter(t => t.type === 'comment').length }}
        </span>
      </button>
    </div>

    <!-- ── DETAILS TAB ── -->
    <template v-if="activeTab === 'details'">
      <!-- Document image -->
      <div v-if="doctype.image_field" class="flex justify-center mb-5">
        <div v-if="imageUrl" class="size-28 rounded-xl overflow-hidden ring-1 ring-border/60 shadow-sm">
          <img :src="imageUrl" :alt="document.name" class="size-full object-cover" />
        </div>
        <div v-else class="size-28 rounded-xl bg-muted/50 ring-1 ring-border/40 flex items-center justify-center">
          <ImageIcon class="size-8 text-muted-foreground/40" />
        </div>
      </div>

      <!-- Actions: Assign + Share + Bookmark -->
      <div class="flex gap-2 mb-5">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="outline" size="sm" class="flex-1 text-foreground" @click="showAssignDialog = true">
                <UserPlus class="size-4 mr-1.5" />
                Призначити
              </Button>
            </TooltipTrigger>
            <TooltipContent>Призначити відповідальну особу</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="outline" size="sm" class="flex-1 text-foreground" @click="showShareDialog = true">
                <Share2 class="size-4 mr-1.5" />
                Поділитися
              </Button>
            </TooltipTrigger>
            <TooltipContent>Надати доступ до документа</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="outline" size="icon" class="size-9 shrink-0"
                :class="bookmark ? 'text-amber-500 border-amber-300 bg-amber-50 dark:bg-amber-950/30' : 'text-foreground'"
                :disabled="bookmarkLoading"
                @click="toggleBookmark">
                <Bookmark class="size-4" :fill="bookmark ? 'currentColor' : 'none'" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{{ bookmark ? 'Прибрати із закладок' : 'Додати до закладок' }}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <!-- Assignees list -->
      <div v-if="assignees.length > 0" class="flex flex-col gap-1.5 mb-4">
        <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Відповідальні</span>
        <div class="flex flex-wrap gap-1.5">
          <Badge v-for="a in assignees" :key="a.id" variant="secondary" class="text-xs gap-1 pr-1">
            {{ a.assigned_to }}
            <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
              @click="removeAssignee(a)">
              <X class="size-2.5" />
            </button>
          </Badge>
        </div>
      </div>

      <!-- Shared with list -->
      <div v-if="sharedWith.length > 0" class="flex flex-col gap-1.5 mb-4">
        <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Доступ</span>
        <div class="flex flex-wrap gap-1.5">
          <Badge v-for="s in sharedWith" :key="s.id" variant="outline" class="text-xs gap-1 pr-1">
            {{ s.user }} · {{ s.permission }}
            <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
              @click="removeShare(s)">
              <X class="size-2.5" />
            </button>
          </Badge>
        </div>
      </div>

      <!-- Tags -->
      <div class="flex flex-col gap-2 mb-4">
        <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
          <Tag class="size-3.5" />
          Теги
        </span>
        <div class="flex flex-wrap gap-1.5">
          <Badge v-for="t in tags" :key="t.id" variant="outline" class="text-xs gap-1 pr-1 text-foreground">
            {{ t.tag }}
            <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
              @click="removeTag(t)">
              <X class="size-2.5" />
            </button>
          </Badge>
        </div>
        <div class="flex gap-1.5">
          <input v-model="tagInput" placeholder="Додати тег..."
            class="flex-1 h-7 rounded-md border border-input bg-transparent px-2.5 text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown="onTagKeydown" />
          <Button variant="outline" size="icon-sm" class="size-7 text-foreground shrink-0"
            :disabled="!tagInput.trim() || tagAdding" @click="addTag">
            <Loader2 v-if="tagAdding" class="size-3.5 animate-spin" />
            <Plus v-else class="size-3.5" />
          </Button>
        </div>
      </div>

      <!-- Meta information -->
      <div class="flex flex-col gap-3 text-sm mb-4">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Інформація</span>
          <PresenceAvatars v-if="users" :users="users" :max="3" />
        </div>
        <div class="flex items-start gap-2.5">
          <User class="size-4 text-muted-foreground shrink-0 mt-0.5" />
          <div>
            <div class="text-foreground">{{ document.owner }}</div>
            <div class="text-xs text-muted-foreground">Автор</div>
          </div>
        </div>
        <div class="flex items-start gap-2.5">
          <Clock class="size-4 text-muted-foreground shrink-0 mt-0.5" />
          <div>
            <div class="text-foreground">{{ createdAt }}</div>
            <div class="text-xs text-muted-foreground">Створено</div>
          </div>
        </div>
        <div v-if="document.modified_by && document.modified_by !== document.owner" class="flex items-start gap-2.5">
          <User class="size-4 text-muted-foreground shrink-0 mt-0.5" />
          <div>
            <div class="text-foreground">{{ document.modified_by }}</div>
            <div class="text-xs text-muted-foreground">Змінив · {{ modifiedAt }}</div>
          </div>
        </div>
        <div v-else class="flex items-start gap-2.5">
          <Clock class="size-4 text-muted-foreground shrink-0 mt-0.5" />
          <div>
            <div class="text-foreground">{{ modifiedAt }}</div>
            <div class="text-xs text-muted-foreground">Останнє редагування</div>
          </div>
        </div>
      </div>

      <!-- Backlinks -->
      <div v-if="links.length > 0" class="flex flex-col gap-2">
        <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          <LinkIcon class="size-3.5 inline-block mr-1 -mt-0.5" />
          Зв'язки ({{ links.length }})
        </span>
        <button v-for="link in links" :key="`${link.source_doctype}-${link.source_id}`"
          class="flex items-center gap-2 text-sm text-foreground/80 hover:text-primary transition-colors group text-left"
          @click="navigateToLink(link)">
          <ChevronRight class="size-3.5 text-muted-foreground/50 group-hover:text-primary transition-colors" />
          <span class="truncate">{{ link.source_doctype }}</span>
          <span class="text-xs text-muted-foreground truncate">{{ link.source_id.slice(0, 8) }}…</span>
        </button>
      </div>
    </template>

    <!-- ── TIMELINE TAB ── -->
    <template v-else>
      <div v-if="timelineLoading" class="flex justify-center py-8">
        <Loader2 class="size-5 animate-spin text-muted-foreground" />
      </div>

      <div v-else class="flex flex-col gap-0">
        <!-- Timeline items -->
        <div v-if="timeline.length === 0" class="py-8 text-center text-sm text-muted-foreground italic">
          Поки що немає активності
        </div>

        <div v-for="item in timeline" :key="item.id" class="relative pl-6 pb-4 group">
          <!-- Connector line -->
          <div class="absolute left-2 top-2 bottom-0 w-px bg-border group-last:hidden" />

          <!-- Icon dot -->
          <div class="absolute left-0 top-1.5 size-4 rounded-full border-2 flex items-center justify-center"
            :class="item.type === 'comment'
              ? 'bg-primary/10 border-primary/30'
              : 'bg-muted border-border'">
            <MessageSquare v-if="item.type === 'comment'" class="size-2 text-primary" />
            <Activity v-else class="size-2 text-muted-foreground" />
          </div>

          <!-- Content -->
          <div class="flex flex-col gap-0.5">
            <div class="flex items-start justify-between gap-2">
              <div class="flex-1">
                <span class="text-xs font-semibold text-foreground">{{ item.user }}</span>
                <span v-if="item.type === 'activity'" class="text-xs text-muted-foreground ml-1">
                  · {{ timelineLabel(item) }}
                </span>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <span class="text-[10px] text-muted-foreground whitespace-nowrap">{{ fmtDate(item.created_at) }}</span>
                <button v-if="item.type === 'comment' && (item.user === auth.user?.email || auth.user?.is_superadmin)"
                  class="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                  @click="deleteComment(item)">
                  <Trash2 class="size-3" />
                </button>
              </div>
            </div>
            <p v-if="item.type === 'comment'" class="text-sm text-foreground bg-muted/50 rounded-lg px-3 py-2 mt-1 whitespace-pre-wrap">
              {{ item.content }}
            </p>
          </div>
        </div>

        <!-- Comment input -->
        <div class="mt-2 flex flex-col gap-2 border-t pt-4">
          <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
            <MessageSquare class="size-3.5" />
            Коментар
          </span>
          <div class="relative">
            <textarea v-model="commentInput" rows="3" placeholder="Напишіть коментар... @email для згадки (Ctrl+Enter щоб надіслати)"
              class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors resize-none"
              @keydown="onCommentKeydown" @input="onCommentInput" />
            <!-- @mention dropdown -->
            <div v-if="mentionDropdown.length"
              class="absolute left-0 right-0 bottom-full mb-1 bg-popover border border-border rounded-lg shadow-lg overflow-hidden z-50">
              <button v-for="(u, i) in mentionDropdown" :key="u.id"
                class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors"
                :class="i === mentionIndex ? 'bg-primary text-primary-foreground' : 'hover:bg-accent text-foreground'"
                @mousedown.prevent="insertMention(u)">
                <span class="font-medium truncate">{{ u.full_name || u.email }}</span>
                <span class="text-xs opacity-70 truncate">{{ u.email }}</span>
              </button>
            </div>
          </div>
          <Button size="sm" :disabled="!commentInput.trim() || commentSending" @click="sendComment" class="self-end">
            <Loader2 v-if="commentSending" class="size-3.5 animate-spin mr-1.5" />
            <Send v-else class="size-3.5 mr-1.5" />
            Надіслати
          </Button>
        </div>
      </div>
    </template>
  </aside>

  <!-- Assign dialog -->
  <Dialog :open="showAssignDialog" @update:open="showAssignDialog = $event">
    <DialogContent class="max-w-sm">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <UserPlus class="size-4" />
          Призначити відповідального
        </DialogTitle>
        <DialogDescription class="sr-only">Введіть email або логін користувача для призначення</DialogDescription>
      </DialogHeader>
      <div class="flex flex-col gap-3 py-1">
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Email або логін</label>
          <input v-model="assignUser" placeholder="user@example.com"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitAssign" />
        </div>
        <div v-if="assignees.length > 0" class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-muted-foreground">Вже призначені</span>
          <div class="flex flex-wrap gap-1.5">
            <Badge v-for="a in assignees" :key="a.id" variant="secondary" class="text-xs gap-1 pr-1">
              {{ a.assigned_to }}
              <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 p-0.5" @click="removeAssignee(a)">
                <X class="size-2.5" />
              </button>
            </Badge>
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" class="text-foreground" @click="showAssignDialog = false">Скасувати</Button>
        <Button :disabled="!assignUser.trim() || assignSaving" @click="submitAssign">
          <Loader2 v-if="assignSaving" class="size-4 animate-spin mr-1.5" />
          Призначити
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Share dialog -->
  <Dialog :open="showShareDialog" @update:open="showShareDialog = $event">
    <DialogContent class="max-w-sm">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Share2 class="size-4" />
          Поділитися документом
        </DialogTitle>
        <DialogDescription class="sr-only">Введіть email або логін користувача та оберіть рівень доступу</DialogDescription>
      </DialogHeader>
      <div class="flex flex-col gap-3 py-1">
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Email або логін</label>
          <input v-model="shareUser" placeholder="user@example.com"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitShare" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Рівень доступу</label>
          <Select :model-value="sharePermission" @update:model-value="sharePermission = $event as 'Read' | 'Write'">
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Read">Читання</SelectItem>
              <SelectItem value="Write">Редагування</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div v-if="sharedWith.length > 0" class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-muted-foreground">Поточний доступ</span>
          <div class="flex flex-col gap-1">
            <div v-for="s in sharedWith" :key="s.id" class="flex items-center justify-between text-sm text-foreground">
              <span>{{ s.user }}</span>
              <div class="flex items-center gap-2">
                <span class="text-xs text-muted-foreground">{{ s.permission === 'Read' ? 'Читання' : 'Редагування' }}</span>
                <button type="button" class="text-muted-foreground hover:text-destructive transition-colors"
                  @click="removeShare(s)">
                  <X class="size-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" class="text-foreground" @click="showShareDialog = false">Скасувати</Button>
        <Button :disabled="!shareUser.trim() || shareSaving" @click="submitShare">
          <Loader2 v-if="shareSaving" class="size-4 animate-spin mr-1.5" />
          Надати доступ
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
