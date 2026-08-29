<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  MessageSquare,
  Activity as ActivityIcon,
  Trash2,
  Loader2,
  Send,
  User,
} from '@lucide/vue'
import { docsApi, type TimelineItem } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import { useAuthStore } from '@/stores/auth'
import type { DocType, GruntDocument, UserPublic } from '@/types'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { formatIntl } from '@/core/datetime'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

const auth = useAuthStore()
const timeline = ref<TimelineItem[]>([])
const timelineLoading = ref(false)

async function loadTimeline() {
  timelineLoading.value = true
  try {
    timeline.value = await docsApi.getTimeline(props.doctype.name, props.document.name)
  } catch { /* silent */ }
  finally { timelineLoading.value = false }
}

const reversedTimeline = computed(() => [...timeline.value].reverse())

const fieldLabelMap = computed(() => {
  const map: Record<string, string> = {}
  for (const f of props.doctype.fields ?? []) {
    if (f.fieldname && f.label) map[f.fieldname] = f.label
  }
  return map
})

function timelineLabel(item: TimelineItem): string {
  if (item.type === 'comment') return item.content ?? ''
  const actionLabels: Record<string, string> = {
    create: 'Створив документ',
    Create: 'Створив документ',
    update: 'Оновив документ',
    Update: 'Оновив документ',
    delete: 'Видалив документ',
    Delete: 'Видалив документ',
    bulk_update: 'Масове оновлення',
    restore: 'Відновив версію',
    transition: 'Змінив статус',
  }
  const base = actionLabels[item.action ?? ''] ?? item.action ?? ''
  if ((item.action === 'Update' || item.action === 'update') && item.details?.changed_fields) {
    const fields = (item.details.changed_fields as string[])
      .map(f => fieldLabelMap.value[f] ?? f)
      .join(', ')
    return `${base}: ${fields}`
  }
  return base
}

function fmtDate(d: string | null) {
  if (!d) return ''
  return formatIntl(d, {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit'
  })
}

const commentInput = ref('')
const commentSending = ref(false)

async function sendComment() {
  const text = commentInput.value.trim()
  if (!text) return
  commentSending.value = true
  try {
    await docsApi.addComment(props.doctype.name, props.document.name, text)
    commentInput.value = ''
    await loadTimeline()
  } catch { /* silent */ }
  finally { commentSending.value = false }
}

async function deleteComment(item: TimelineItem) {
  try {
    await docsApi.deleteComment(props.doctype.name, props.document.name, item.id)
    timeline.value = timeline.value.filter(t => t.id !== item.id)
  } catch { /* silent */ }
}

// ── @mention autocomplete logic (retained for functionality) ─────────────────
const allUsers = ref<UserPublic[]>([])
const mentionDropdown = ref<UserPublic[]>([])
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
          u.full_name?.toLowerCase().includes(mentionQuery.value)
        )
        .slice(0, 6)
      mentionIndex.value = 0
    })
  } else {
    mentionDropdown.value = []
  }
}

function insertMention(user: UserPublic) {
  const before = commentInput.value
  const pos = before.lastIndexOf('@' + mentionQuery.value)
  commentInput.value = before.slice(0, pos) + `@${user.email} ` + before.slice(pos + 1 + mentionQuery.value.length)
  mentionDropdown.value = []
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

defineExpose({ loadTimeline })
onMounted(loadTimeline)
</script>

<template>
  <div v-if="timelineLoading" class="flex justify-center py-10">
    <Loader2 class="size-6 animate-spin text-primary/60" />
  </div>

  <div v-else class="flex flex-col gap-6">
    <!-- Comment input -->
    <div class="flex flex-col gap-3 group/comment bg-muted/20 p-4 rounded-lg border border-border/40">
      <div class="flex items-center gap-2 px-1">
        <MessageSquare class="size-4 text-primary/60" />
        <span class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Додати коментар</span>
      </div>
      <div class="relative">
        <Textarea v-model="commentInput" rows="3"
          placeholder="Напишіть коментар... @ для згадки"
          class="w-full !text-sm !shadow-inner !bg-background !border-border/60 focus:!border-primary/50 transition-all resize-none"
          @keydown="onCommentKeydown" @input="onCommentInput" />

        <!-- Mentions -->
        <div v-if="mentionDropdown.length"
          class="absolute left-0 right-0 bottom-full mb-2 bg-popover border border-border rounded-lg shadow-md overflow-hidden z-50 animate-in fade-in slide-in-from-bottom-2 duration-200">
          <div class="px-3 py-2 bg-muted/50 border-b border-border text-xs font-semibold uppercase tracking-widest text-muted-foreground/80">Згадати користувача</div>
          <button v-for="(u, i) in mentionDropdown" :key="u.id"
            class="w-full flex items-center gap-3 px-3 py-2.5 text-left transition-all border-b border-border/40 last:border-0"
            :class="i === mentionIndex ? 'bg-primary text-primary-foreground' : 'hover:bg-accent hover:text-foreground'"
            @mousedown.prevent="insertMention(u)">
            <Avatar class="!size-7 shrink-0">
              <AvatarFallback :class="i === mentionIndex ? 'bg-primary-foreground/20 text-white' : ''"><User class="size-3.5" /></AvatarFallback>
            </Avatar>
            <div class="flex flex-col min-w-0">
                <span class="font-semibold truncate text-xs">{{ u.full_name || u.email }}</span>
                <span class="text-xs opacity-70 truncate">{{ u.email }}</span>
            </div>
          </button>
        </div>
      </div>
      <div class="flex items-center justify-between px-1">
          <span class="text-xs text-muted-foreground/60 italic">Ctrl+Enter щоб надіслати</span>
          <Button size="sm" :disabled="!commentInput.trim() || commentSending" @click="sendComment" class="px-5">
            <Loader2 v-if="commentSending" class="size-3.5 animate-spin mr-2" />
            <Send v-else class="size-3.5 mr-2" />
            <span class="font-semibold">Надіслати</span>
          </Button>
      </div>
    </div>

    <div v-if="timeline.length === 0" class="py-12 text-center text-muted-foreground/60 italic bg-muted/20 rounded-lg border border-dashed border-border/40">
      Поки що немає активності
    </div>

    <!-- Timeline -->
    <div class="w-full">
      <div v-for="(item, idx) in reversedTimeline" :key="idx" class="flex gap-2 group">
        <div class="flex flex-col items-center shrink-0">
          <span class="flex size-7 items-center justify-center rounded-full shadow-sm ring-1 ring-border/40"
            :class="item.type === 'comment' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'">
            <MessageSquare v-if="item.type === 'comment'" class="size-3" />
            <ActivityIcon v-else class="size-3" />
          </span>
          <div v-if="idx < reversedTimeline.length - 1" class="w-px flex-1 bg-border/40 my-1" />
        </div>
        <div class="flex flex-col gap-1 mb-6 pl-2 min-w-0 flex-1">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-semibold text-foreground truncate">{{ item.user }}</span>
            <div class="flex items-center gap-1.5 shrink-0">
                <span class="text-xs font-medium text-muted-foreground/60 uppercase">{{ fmtDate(item.created_at) }}</span>
                <button v-if="item.type === 'comment' && (item.user === auth.user?.email || auth.user?.is_superadmin)"
                    class="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-destructive/10 hover:text-destructive rounded"
                    @click="deleteComment(item)">
                    <Trash2 class="size-3" />
                </button>
            </div>
          </div>
          <span v-if="item.type === 'activity'" class="text-xs font-medium text-muted-foreground leading-relaxed">
            {{ timelineLabel(item) }}
          </span>
          <p v-if="item.type === 'comment'"
            class="text-foreground bg-muted/40 border border-border/20 rounded-lg px-4 py-2.5 mt-1 whitespace-pre-wrap leading-relaxed shadow-sm">
            {{ item.content }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
