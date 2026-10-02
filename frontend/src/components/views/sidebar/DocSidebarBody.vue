<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { Bell, Bookmark, Check, Copy, ExternalLink, Printer } from '@lucide/vue'
import type { DocType, GruntDocument } from '@/types'
import type { PresenceUser } from '@/core/composables/usePresence'
import { useDocSidebar } from './useDocSidebar'
import { useToast } from '@/core/composables/useToast'
import { formatFull, formatRelative } from '@/core/datetime'
import { resolveStatusBadge, statusBadgeFor, statusToneClass } from '@/core/status'
import SidebarImage from './SidebarImage.vue'
import SidebarPeople from './SidebarPeople.vue'
import SidebarTags from './SidebarTags.vue'
import SidebarPersonCard from './SidebarPersonCard.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from '@/components/ui/item'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Toggle } from '@/components/ui/toggle'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const { t } = useI18n()

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
  /** Value of `image_field` in the form (may be unsaved); falls back to the saved document. */
  imageUrl?: string | null
  /** Upload / replace / remove the image from the sidebar. */
  imageEditable?: boolean
}>()

const emit = defineEmits<{ 'set-image': [url: string | null] }>()

const toast = useToast()
const sb = useDocSidebar(
  () => props.doctype.name,
  () => props.document.name,
)

const image = computed(() => {
  if (props.imageUrl !== undefined) return props.imageUrl || null
  const field = props.doctype.image_field
  const val = field ? props.document[field] : null
  return typeof val === 'string' && val ? val : null
})
const isBookmarked = computed(() => !!sb.bundle.value.bookmark)
const isFollowing = computed(() => !!sb.bundle.value.follow)
// Set by the server while the document is a public page (web view, WebPage, WebForm).
const webUrl = computed(() => {
  const url = props.document.__web_url
  return typeof url === 'string' && url ? url : null
})
const webPath = computed(() => {
  if (!webUrl.value) return ''
  try {
    return new URL(webUrl.value, window.location.origin).pathname
  } catch {
    return webUrl.value
  }
})

// ── Status badges ───────────────────────────────────────────────────────────
const statusBadge = computed(() => resolveStatusBadge(props.doctype, props.document))
// Workflow state, when it lives in a field other than the status one (otherwise
// the badge above already is the state). The form hides that field; its
// transitions are in the form header.
const workflowBadge = computed(() => {
  const field = props.doctype.workflow_state_field
  if (!field || field === (props.doctype.status_field || 'status')) return null
  return statusBadgeFor(props.doctype, props.document[field])
})
const docstatusBadge = computed(() => {
  if (!props.doctype.is_submittable) return null
  return (
    [
      { label: t('Draft'), class: statusToneClass('secondary') },
      { label: t('Submitted'), class: statusToneClass('info') },
      { label: t('status|Cancelled'), class: statusToneClass('danger') },
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
    toast.error(t('Could not copy'))
  }
}

// ── Who / when rows ─────────────────────────────────────────────────────────
const people = computed(() => [
  { key: 'created', label: t('created'), email: props.document.owner, at: props.document.created_at },
  {
    key: 'modified',
    label: t('modified'),
    email: props.document.modified_by || props.document.owner,
    at: props.document.modified_at,
  },
])

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
</script>

<template>
  <div class="flex flex-col gap-4 text-sm">
    <SidebarImage
      v-if="doctype.image_field"
      :url="image"
      :editable="!!imageEditable"
      :doctype="doctype.name"
      :doc-id="document.name"
      :alt="bookmarkTitle()"
      @change="emit('set-image', $event)"
    />

    <!-- Properties -->
    <dl class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-2.5">
      <template v-if="statusBadge">
        <dt class="text-muted-foreground">{{ t('Status') }}</dt>
        <dd>
          <Badge variant="outline" :class="statusBadge.class">
            {{ statusBadge.label }}
          </Badge>
        </dd>
      </template>

      <template v-if="workflowBadge">
        <dt class="text-muted-foreground">{{ t('State') }}</dt>
        <dd>
          <Badge variant="outline" :class="workflowBadge.class">
            {{ workflowBadge.label }}
          </Badge>
        </dd>
      </template>

      <template v-if="docstatusBadge">
        <dt class="text-muted-foreground">{{ t('Document') }}</dt>
        <dd>
          <Badge variant="outline" :class="docstatusBadge.class">{{ docstatusBadge.label }}</Badge>
        </dd>
      </template>

      <dt class="text-muted-foreground">ID</dt>
      <dd class="flex min-w-0 items-center gap-1">
        <code class="truncate font-mono text-xs">{{ document.name }}</code>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button variant="ghost" size="icon-xs" class="text-muted-foreground" :aria-label="t('Copy ID')" @click="copyId">
              <Check v-if="copied" class="text-success" />
              <Copy v-else />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{{ copied ? t('Copied') : t('Copy ID') }}</TooltipContent>
        </Tooltip>
      </dd>

      <template v-if="webUrl">
        <dt class="text-muted-foreground">{{ t('On website') }}</dt>
        <dd class="min-w-0">
          <Tooltip>
            <TooltipTrigger as-child>
              <a
                :href="webUrl"
                target="_blank"
                rel="noopener"
                class="group flex items-center gap-1 rounded-sm outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-ring/50"
              >
                <span class="truncate font-mono text-xs">{{ webPath }}</span>
                <ExternalLink class="size-3 shrink-0 text-muted-foreground group-hover:text-primary" />
              </a>
            </TooltipTrigger>
            <TooltipContent class="max-w-80 break-all">{{ webUrl }}</TooltipContent>
          </Tooltip>
        </dd>
      </template>
    </dl>

    <!-- Who / when: full width so long names fit -->
    <ItemGroup class="-mx-2 gap-0.5">
      <Item v-for="p in people" :key="p.key" size="sm" class="gap-2.5 px-2 py-1.5">
        <SidebarPersonCard :sb="sb" :email="p.email">
          <ItemMedia>
            <Avatar class="size-7">
              <AvatarImage v-if="sb.personAvatar(p.email)" :src="sb.personAvatar(p.email)!" />
              <AvatarFallback class="text-[10px]">{{ sb.personInitials(p.email) }}</AvatarFallback>
            </Avatar>
          </ItemMedia>
        </SidebarPersonCard>
        <ItemContent class="min-w-0 gap-0">
          <ItemTitle class="w-full">
            <SidebarPersonCard :sb="sb" :email="p.email">
              <span class="truncate">{{ sb.personName(p.email) }}</span>
            </SidebarPersonCard>
          </ItemTitle>
          <ItemDescription class="text-xs">
            <Tooltip>
              <TooltipTrigger as-child>
                <time :datetime="p.at ?? undefined">{{ p.label }} · {{ formatRelative(p.at) }}</time>
              </TooltipTrigger>
              <TooltipContent>{{ formatFull(p.at) }}</TooltipContent>
            </Tooltip>
          </ItemDescription>
        </ItemContent>
      </Item>
    </ItemGroup>

    <Separator />

    <template v-if="sb.loaded.value || !sb.loading.value">
      <SidebarPeople :sb="sb" :workspace="workspace" />
      <Separator />
      <SidebarTags :sb="sb" />
    </template>
    <div v-else class="flex flex-col gap-3">
      <Skeleton class="h-4 w-24" />
      <Skeleton class="h-8 w-full" />
      <Skeleton class="h-4 w-16" />
      <Skeleton class="h-5 w-2/3" />
    </div>

    <Separator />

    <!-- Actions -->
    <ButtonGroup class="w-full">
      <Tooltip>
        <TooltipTrigger as-child>
          <Toggle
            variant="outline"
            size="sm"
            class="flex-1 data-[state=on]:text-primary"
            :model-value="isFollowing"
            @update:model-value="sb.toggleFollow()"
          >
            <Bell :fill="isFollowing ? 'currentColor' : 'none'" />
            {{ isFollowing ? t('Following') : t('Follow') }}
          </Toggle>
        </TooltipTrigger>
        <TooltipContent>
          {{ isFollowing ? t('You get notified about changes and comments') : t('Get notified about changes and comments') }}
        </TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger as-child>
          <Toggle
            variant="outline"
            size="sm"
            class="data-[state=on]:text-warning"
            :model-value="isBookmarked"
            :aria-label="isBookmarked ? t('Bookmarked') : t('Bookmark')"
            @update:model-value="sb.toggleBookmark(bookmarkTitle())"
          >
            <Bookmark :fill="isBookmarked ? 'currentColor' : 'none'" />
          </Toggle>
        </TooltipTrigger>
        <TooltipContent>{{ isBookmarked ? t('Bookmarked') : t('Bookmark') }}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger as-child>
          <Button variant="outline" size="icon-sm" :aria-label="t('Print')" @click="printDoc">
            <Printer />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{{ t('Print') }}</TooltipContent>
      </Tooltip>
    </ButtonGroup>
  </div>
</template>
