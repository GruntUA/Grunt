<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted } from 'vue'
import {
  MessageSquare,
  Activity as ActivityIcon,
  Trash2,
  Send,
} from '@lucide/vue'
import { docsApi, type TimelineItem, type DocVersionChange } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/core/composables/useDialog'
import type { DocType, GruntDocument, UserPublic } from '@/types'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { Spinner } from '@/components/ui/spinner'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from '@/components/ui/item'
import { formatIntl } from '@/core/datetime'

const { t } = useI18n()

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

const emit = defineEmits<{
  /** A previous version was restored — the document's own data is now stale. */
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
    // generic label, so just say how many — the alternative is "[object
    // Object]" repeated N times.
    if (val.some(v => v !== null && typeof v === 'object')) return t('{n} rows', { n: String(val.length) })
    return val.map(String).join(', ')
  }
  return String(val)
}

/** Prefer the resolved Link-field title (old_label/new_label) over the raw stored id. */
function changeValue(change: DocVersionChange, key: 'old' | 'new'): string {
  const label = key === 'old' ? change.old_label : change.new_label
  return label ?? formatDiffValue(change[key])
}

function versionChangeText(item: TimelineItem): string {
  return (item.changes ?? [])
    .map(c => `${fieldLabelMap.value[c.field] ?? c.field}: ${changeValue(c, 'old')} → ${changeValue(c, 'new')}`)
    .join('; ')
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

    <!-- Timeline -->
    <div v-else class="w-full">
      <div v-for="(item, idx) in reversedTimeline" :key="idx" class="flex gap-3 group">
        <div class="flex flex-col items-center shrink-0">
          <span class="flex size-6 items-center justify-center rounded-full border"
            :class="item.type === 'comment' ? 'bg-primary/10 text-primary border-primary/20' : 'bg-muted text-muted-foreground'">
            <MessageSquare v-if="item.type === 'comment'" class="size-3" />
            <ActivityIcon v-else class="size-3" />
          </span>
          <div v-if="idx < reversedTimeline.length - 1" class="w-px flex-1 bg-border my-1" />
        </div>
        <div class="flex flex-col gap-1 pb-5 min-w-0 flex-1">
          <div class="flex items-center justify-between gap-2">
            <span class="font-medium text-foreground truncate">{{ item.user }}</span>
            <div class="flex items-center gap-1 shrink-0">
                <span class="text-muted-foreground">{{ fmtDate(item.created_at) }}</span>
                <Button v-if="item.type === 'comment' && (item.user === auth.user?.email || auth.isSystemManager)"
                    variant="ghost" size="icon-xs"
                    class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-destructive/10 hover:text-destructive [@media(hover:none)]:opacity-100"
                    :aria-label="t('Delete comment')"
                    @click="deleteComment(item)">
                    <Trash2 />
                </Button>
            </div>
          </div>
          <span v-if="item.type === 'activity'" class="text-muted-foreground">
            {{ timelineLabel(item) }}
          </span>
          <Button v-if="item.type === 'version'" variant="link"
            class="h-auto w-fit justify-start p-0 font-normal whitespace-normal text-left text-muted-foreground hover:text-foreground"
            @click="openVersionDiff(item)">
            {{ versionChangeText(item) }}
          </Button>
          <p v-if="item.type === 'comment'"
            class="text-foreground rounded-md border bg-muted/40 px-3 py-2 whitespace-pre-wrap">
            {{ item.content }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
