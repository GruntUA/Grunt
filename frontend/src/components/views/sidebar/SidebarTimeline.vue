<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted } from 'vue'
import { ArrowRight, Trash2, Send, Reply } from '@lucide/vue'
import { docsApi, type TimelineItem, type DocVersionChange } from '@/core/api/docs'
import { authApi } from '@/core/api/auth-admin'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/core/composables/useDialog'
import type { Colleague, DocType, GruntDocument } from '@/types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { Spinner } from '@/components/ui/spinner'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from '@/components/ui/item'
import { formatFull, formatIntl } from '@/core/datetime'
import { tn } from '@/plugins/i18n'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import TimelineChanges from './TimelineChanges.vue'
import { htmlToLine, htmlToText, looksLikeHtml } from '@/lib/htmlText'
import { statusBadgeFor } from '@/core/status'
import { Badge } from '@/components/ui/badge'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useLocalStorage } from '@vueuse/core'

const { t } = useI18n()

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

const emit = defineEmits<{
  /** A previous version was restored - the document's own data is now stale. */
  restored: []
}>()

const auth = useAuthStore()
const dialog = useDialog()
const timeline = ref<TimelineItem[]>([])
const timelineLoading = ref(false)

async function loadTimeline() {
  timelineLoading.value = true
  try {
    timeline.value = await docsApi.getTimeline(props.doctype.name, props.document.name)
  } catch { /* silent */ }
  finally { timelineLoading.value = false }
}

// A Date/Datetime "change" that is the same instant in another timezone
// notation (e.g. +00:00 -> +03:00) is not a change for the reader.
function isRealChange(c: DocVersionChange): boolean {
  const type = props.doctype.fields?.find((f) => f.fieldname === c.field)?.fieldtype
  if ((type === 'Date' || type === 'Datetime') && typeof c.old === 'string' && typeof c.new === 'string') {
    const a = Date.parse(c.old)
    const b = Date.parse(c.new)
    if (!Number.isNaN(a) && a === b) return false
  }
  return true
}

const isWorkflow = (item: TimelineItem) => item.type === 'activity' && item.action?.toLowerCase() === 'workflow'

// A workflow action also writes a version that only flips the state field -
// the workflow entry already says that, so the version is dropped.
function isWorkflowEcho(item: TimelineItem, changes: DocVersionChange[]): boolean {
  const stateField = props.doctype.workflow_state_field
  if (!stateField || changes.some((c) => c.field !== stateField)) return false
  const at = Date.parse(item.created_at ?? '')
  return timeline.value.some(
    (w) => isWorkflow(w) && w.user === item.user && Math.abs(Date.parse(w.created_at ?? '') - at) < 10_000,
  )
}

// Newest first; versions keep only real changes and drop out when none are left.
const reversedTimeline = computed(() =>
  [...timeline.value].reverse().flatMap((item) => {
    if (item.type !== 'version') return [item]
    const changes = (item.changes ?? []).filter(isRealChange)
    return changes.length && !isWorkflowEcho(item, changes) ? [{ ...item, changes }] : []
  }),
)

type TimelineFilter = 'all' | 'comments' | 'changes'
const filter = useLocalStorage<TimelineFilter>('grunt.timeline.filter', 'all')

const filterCounts = computed(() => {
  const comments = reversedTimeline.value.filter((i) => i.type === 'comment').length
  return { all: reversedTimeline.value.length, comments, changes: reversedTimeline.value.length - comments }
})

// Replies sit under their root comment, oldest first, instead of in the feed.
const repliesOf = computed(() => {
  const roots = new Set(timeline.value.filter((i) => i.type === 'comment').map((i) => i.id))
  const map: Record<string, TimelineItem[]> = {}
  for (const item of timeline.value) {
    if (item.type === 'comment' && item.parent_comment && roots.has(item.parent_comment)) {
      (map[item.parent_comment] ??= []).push(item)
    }
  }
  return map
})

const isReply = (item: TimelineItem) =>
  item.type === 'comment' && !!item.parent_comment && !!repliesOf.value[item.parent_comment]

const visibleTimeline = computed(() => {
  const feed = reversedTimeline.value.filter((i) => !isReply(i))
  if (filter.value === 'all') return feed
  const wantComments = filter.value === 'comments'
  return feed.filter((i) => (i.type === 'comment') === wantComments)
})

function workflowState(item: TimelineItem, key: 'from' | 'to') {
  const state = item.details?.[key]
  if (state == null || state === '') return null
  return statusBadgeFor(props.doctype, state) ?? { label: String(state), class: '' }
}

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
    create: t('Created the document'),
    Create: t('Created the document'),
    update: t('Updated the document'),
    Update: t('Updated the document'),
    delete: t('Deleted the document'),
    Delete: t('Deleted the document'),
    bulk_update: t('Bulk Update'),
    restore: t('Restored a version'),
    transition: t('Changed the status'),
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

function formatDiffValue(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'boolean') return val ? t('Yes') : t('No')
  if (Array.isArray(val)) {
    if (!val.length) return '—'
    // Child-table / MultiLink snapshots: rows of objects have no single
    // generic label, so just say how many - the alternative is "[object
    // Object]" repeated N times.
    if (val.some(v => v !== null && typeof v === 'object')) return t('{n} rows', { n: String(val.length) })
    return val.map(String).join(', ')
  }
  const s = String(val)
  return looksLikeHtml(s) ? htmlToLine(s) || '—' : s
}

/** Prefer the resolved Link-field title (old_label/new_label) over the raw stored id. */
function changeValue(change: DocVersionChange, key: 'old' | 'new'): string {
  const label = key === 'old' ? change.old_label : change.new_label
  return label ?? formatDiffValue(change[key])
}

function initials(item: TimelineItem): string {
  const parts = (item.user_name || item.user || '?').split(/[\s@.]+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts[1]?.[0] ?? '')).toUpperCase()
}

/** Short action text after the author's name. */
function summary(item: TimelineItem): string {
  if (item.type === 'comment') return t('commented')
  if (item.type === 'version') {
    const n = item.changes?.length ?? 0
    return tn('changed {n} field', 'changed {n} fields', n)
  }
  if (isWorkflow(item)) {
    const action = item.details?.action
    return action ? t('applied «{action}»', { action: String(action) }) : t('changed the state')
  }
  const label = timelineLabel(item)
  return label.charAt(0).toLocaleLowerCase() + label.slice(1)
}

async function openVersionDiff(item: TimelineItem) {
  const changes = item.changes ?? []
  if (!changes.length) return
  await dialog.form({
    title: item.version ? t('Version {n}', { n: String(item.version) }) : t('Changes'),
    size: 'large',
    fields: [{
      fieldname: 'diff',
      label: '',
      fieldtype: 'Table',
      selectable: false,
      searchable: false,
      rowKey: 'field',
      rows: changes.map(c => ({
        field: fieldLabelMap.value[c.field] ?? c.field,
        old: changeValue(c, 'old'),
        new: changeValue(c, 'new'),
      })),
      columns: [
        { key: 'field', label: t('Field'), width: '30%' },
        { key: 'old', label: t('Before') },
        { key: 'new', label: t('After') },
      ],
    }],
    buttons: [{
      label: t('Restore this version'),
      variant: 'outline',
      action: async (ctx) => {
        const ok = await ctx.confirm(t('Restore the document to this version? Current field values will be replaced.'))
        if (!ok) return
        try {
          await docsApi.restoreVersion(props.doctype.name, props.document.name, item.id)
          await loadTimeline()
          emit('restored')
          ctx.close()
        } catch { /* silent */ }
      },
    }],
  })
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
    // A deleted root takes its replies along.
    timeline.value = timeline.value.filter(t => t.id !== item.id && t.parent_comment !== item.id)
  } catch { /* silent */ }
}

const canDelete = (item: TimelineItem) =>
  item.type === 'comment' && (item.user === auth.user?.email || auth.isSystemManager)

// Reply box - one open at a time, under the thread it answers.
const replyTo = ref<string | null>(null)
const replyInput = ref('')
const replySending = ref(false)

function openReply(item: TimelineItem) {
  replyTo.value = item.id
  replyInput.value = ''
}

async function sendReply() {
  const text = replyInput.value.trim()
  if (!text || !replyTo.value) return
  replySending.value = true
  try {
    await docsApi.addComment(props.doctype.name, props.document.name, text, replyTo.value)
    replyTo.value = null
    replyInput.value = ''
    await loadTimeline()
  } catch { /* silent */ }
  finally { replySending.value = false }
}

function onReplyKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') replyTo.value = null
  else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    sendReply()
  }
}

// @mention autocomplete logic (retained for functionality)
const allUsers = ref<Colleague[]>([])
const mentionDropdown = ref<Colleague[]>([])
const mentionIndex = ref(0)
const mentionQuery = ref('')

async function ensureUsers() {
  if (allUsers.value.length) return
  try { allUsers.value = await authApi.listColleagues() } catch { /* silent */ }
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

function insertMention(user: Colleague) {
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
    <Spinner class="size-5 text-muted-foreground" />
  </div>

  <div v-else class="flex flex-col gap-5">
    <!-- Comment input -->
    <div class="flex flex-col gap-2">
      <!-- Mentions: anchored to the textarea, which keeps focus and drives the
           highlight with the arrow keys (onCommentKeydown). -->
      <Popover :open="mentionDropdown.length > 0" @update:open="(v) => { if (!v) mentionDropdown = [] }">
        <PopoverAnchor as-child>
          <Textarea v-model="commentInput" rows="3"
            :placeholder="t('Write a comment... @ to mention')"
            class="resize-none"
            @keydown="onCommentKeydown" @input="onCommentInput" />
        </PopoverAnchor>
        <PopoverContent side="top" align="start" class="w-(--reka-popper-anchor-width) p-1"
          @open-auto-focus.prevent @close-auto-focus.prevent>
          <div class="px-2 py-1.5 text-xs font-medium text-muted-foreground">{{ t('Mention a user') }}</div>
          <ItemGroup class="max-h-56 overflow-y-auto">
            <Item v-for="(u, i) in mentionDropdown" :key="u.id" as="button" type="button" size="sm"
              class="w-full flex-nowrap gap-2 px-2 py-1.5 text-left hover:bg-accent hover:text-accent-foreground"
              :class="i === mentionIndex && 'bg-accent text-accent-foreground'"
              @mousedown.prevent="insertMention(u)">
              <ItemMedia>
                <Avatar class="size-6">
                  <AvatarFallback class="text-[10px]">{{ (u.full_name || u.email).slice(0, 2).toUpperCase() }}</AvatarFallback>
                </Avatar>
              </ItemMedia>
              <ItemContent class="min-w-0 gap-0">
                <ItemTitle class="w-full"><span class="truncate">{{ u.full_name || u.email }}</span></ItemTitle>
                <ItemDescription v-if="u.full_name" class="truncate text-xs">{{ u.email }}</ItemDescription>
              </ItemContent>
            </Item>
          </ItemGroup>
        </PopoverContent>
      </Popover>
      <div class="flex items-center justify-between">
          <KbdGroup class="text-xs text-muted-foreground">
            <Kbd>Ctrl</Kbd><Kbd>Enter</Kbd>
            <span>{{ t('to send') }}</span>
          </KbdGroup>
          <Button size="sm" :disabled="!commentInput.trim() || commentSending" @click="sendComment">
            <Spinner v-if="commentSending" />
            <Send v-else />
            {{ t('Send') }}
          </Button>
      </div>
    </div>

    <div v-if="timeline.length === 0" class="py-8 text-center text-muted-foreground">
      {{ t('No activity yet') }}
    </div>

    <ToggleGroup v-else type="single" variant="outline" size="sm" class="self-start"
      :model-value="filter" @update:model-value="(v) => { if (v) filter = v as TimelineFilter }">
      <ToggleGroupItem v-for="f in (['all', 'comments', 'changes'] as const)" :key="f" :value="f" class="px-2.5">
        {{ f === 'all' ? t('All') : f === 'comments' ? t('Comments') : t('Changes') }}
        <span class="text-muted-foreground tabular-nums">{{ filterCounts[f] }}</span>
      </ToggleGroupItem>
    </ToggleGroup>

    <div v-if="timeline.length && !visibleTimeline.length" class="py-8 text-center text-muted-foreground">
      {{ filter === 'comments' ? t('No comments yet') : t('No changes yet') }}
    </div>

    <!-- Timeline -->
    <ol v-if="visibleTimeline.length" class="w-full">
      <li v-for="(item, idx) in visibleTimeline" :key="item.id ?? idx" class="group flex gap-3">
        <div class="flex shrink-0 flex-col items-center">
          <Avatar class="size-7">
            <AvatarImage v-if="item.user_avatar" :src="item.user_avatar" />
            <AvatarFallback class="text-[10px]">{{ initials(item) }}</AvatarFallback>
          </Avatar>
          <div v-if="idx < visibleTimeline.length - 1" class="my-1 w-px flex-1 bg-border" />
        </div>
        <div class="flex min-w-0 flex-1 flex-col gap-2 pb-6">
          <div class="flex min-h-7 items-center gap-2">
            <p class="flex min-w-0 flex-1 items-baseline gap-1.5 text-sm">
              <span class="shrink-0 font-medium">{{ item.user_name || item.user }}</span>
              <span class="truncate text-muted-foreground">{{ summary(item) }}</span>
            </p>
            <Tooltip>
              <TooltipTrigger as-child>
                <time class="shrink-0 text-xs text-muted-foreground" :datetime="item.created_at ?? undefined">
                  {{ fmtDate(item.created_at) }}
                </time>
              </TooltipTrigger>
              <TooltipContent>{{ formatFull(item.created_at) }}</TooltipContent>
            </Tooltip>
            <Button v-if="item.type === 'comment'" variant="ghost" size="icon-xs"
              class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
              :aria-label="t('Reply')"
              @click="openReply(item)">
              <Reply />
            </Button>
            <Button v-if="canDelete(item)"
              variant="ghost" size="icon-xs"
              class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-destructive/10 hover:text-destructive [@media(hover:none)]:opacity-100"
              :aria-label="t('Delete comment')"
              @click="deleteComment(item)">
              <Trash2 />
            </Button>
          </div>
          <TimelineChanges v-if="item.type === 'version' && item.changes?.length"
            :changes="item.changes" :fields="doctype.fields ?? []" @compare="openVersionDiff(item)" />
          <div v-if="isWorkflow(item) && (workflowState(item, 'from') || workflowState(item, 'to'))"
            class="flex flex-wrap items-center gap-1.5">
            <Badge v-if="workflowState(item, 'from')" variant="outline" :class="workflowState(item, 'from')!.class">
              {{ workflowState(item, 'from')!.label }}
            </Badge>
            <ArrowRight class="size-3.5 text-muted-foreground" />
            <Badge v-if="workflowState(item, 'to')" variant="outline" :class="workflowState(item, 'to')!.class">
              {{ workflowState(item, 'to')!.label }}
            </Badge>
          </div>
          <p v-if="item.type === 'comment'"
            class="rounded-md border bg-muted/40 px-3 py-2 text-sm break-words whitespace-pre-line">
            {{ htmlToText(item.content ?? '') }}
          </p>

          <!-- Thread: replies, then the reply box -->
          <ol v-if="repliesOf[item.id]?.length" class="flex flex-col gap-3 border-l pl-3">
            <li v-for="reply in repliesOf[item.id]" :key="reply.id" class="group/reply flex gap-2">
              <Avatar class="size-6">
                <AvatarImage v-if="reply.user_avatar" :src="reply.user_avatar" />
                <AvatarFallback class="text-[9px]">{{ initials(reply) }}</AvatarFallback>
              </Avatar>
              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <div class="flex min-h-6 items-center gap-2 text-sm">
                  <span class="min-w-0 flex-1 truncate font-medium">{{ reply.user_name || reply.user }}</span>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <time class="shrink-0 text-xs text-muted-foreground" :datetime="reply.created_at ?? undefined">
                        {{ fmtDate(reply.created_at) }}
                      </time>
                    </TooltipTrigger>
                    <TooltipContent>{{ formatFull(reply.created_at) }}</TooltipContent>
                  </Tooltip>
                  <Button v-if="canDelete(reply)" variant="ghost" size="icon-xs"
                    class="opacity-0 group-hover/reply:opacity-100 focus-visible:opacity-100 hover:bg-destructive/10 hover:text-destructive [@media(hover:none)]:opacity-100"
                    :aria-label="t('Delete comment')"
                    @click="deleteComment(reply)">
                    <Trash2 />
                  </Button>
                </div>
                <p class="text-sm break-words whitespace-pre-line">{{ htmlToText(reply.content ?? '') }}</p>
              </div>
            </li>
          </ol>
          <div v-if="replyTo === item.id" class="flex flex-col gap-2 pl-3">
            <Textarea v-model="replyInput" rows="2" autofocus class="resize-none"
              :placeholder="t('Write a reply...')" @keydown="onReplyKeydown" />
            <div class="flex justify-end gap-2">
              <Button size="sm" variant="ghost" @click="replyTo = null">{{ t('Cancel') }}</Button>
              <Button size="sm" :disabled="!replyInput.trim() || replySending" @click="sendReply">
                <Spinner v-if="replySending" />
                <Send v-else />
                {{ t('Reply') }}
              </Button>
            </div>
          </div>
        </div>
      </li>
    </ol>
  </div>
</template>
