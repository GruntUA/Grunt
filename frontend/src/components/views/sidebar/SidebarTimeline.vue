<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import {
  MessageSquare,
  Activity,
  Trash2,
  Loader2,
  Send,
} from '@lucide/vue'
import { docsApi, type TimelineItem } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import { useAuthStore } from '@/stores/auth'
import type { DocType, GruntDocument, GruntUserPublic } from '@/types'

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
    timeline.value = await docsApi.getTimeline(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { timelineLoading.value = false }
}

function timelineLabel(item: TimelineItem): string {
  if (item.type === 'comment') return item.content ?? ''
  const labels: Record<string, string> = {
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
  return labels[item.action ?? ''] ?? item.action ?? ''
}

function fmtDate(d: string | null) {
  return d ? new Date(d).toLocaleString('uk-UA') : ''
}

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
  <div v-if="timelineLoading" class="flex justify-center py-8">
    <Loader2 class="size-5 animate-spin text-muted-foreground" />
  </div>

  <div v-else class="flex flex-col gap-0">
    <div v-if="timeline.length === 0" class="py-8 text-center text-sm text-muted-foreground italic">
      Поки що немає активності
    </div>

    <div v-for="item in timeline" :key="item.id" class="relative pl-6 pb-4 group">
      <div class="absolute left-2 top-2 bottom-0 w-px bg-border group-last:hidden" />
      <div class="absolute left-0 top-1.5 size-4 rounded-full border-2 flex items-center justify-center"
        :class="item.type === 'comment' ? 'bg-primary/10 border-primary/30' : 'bg-muted border-border'">
        <MessageSquare v-if="item.type === 'comment'" class="size-2 text-primary" />
        <Activity v-else class="size-2 text-muted-foreground" />
      </div>

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
        <p v-if="item.type === 'comment'"
          class="text-sm text-foreground bg-muted/50 rounded-lg px-3 py-2 mt-1 whitespace-pre-wrap">
          {{ item.content }}
        </p>
      </div>
    </div>

    <div class="mt-2 flex flex-col gap-2 border-t pt-4">
      <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
        <MessageSquare class="size-3.5" />
        Коментар
      </span>
      <div class="relative">
        <textarea v-model="commentInput" rows="3"
          placeholder="Напишіть коментар... @email для згадки (Ctrl+Enter щоб надіслати)"
          class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors resize-none"
          @keydown="onCommentKeydown" @input="onCommentInput" />
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
