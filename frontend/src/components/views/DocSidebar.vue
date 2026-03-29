<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { DocType, GruntDocument } from '@/types'
import { docsApi, type BacklinkItem } from '@/core/api/docs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
}>()

const router = useRouter()

// Image
const imageUrl = computed(() => {
  if (!props.doctype.image_field) return null
  const val = props.document[props.doctype.image_field]
  return typeof val === 'string' && val ? val : null
})

// Meta info
const createdAt = computed(() => {
  const d = props.document.created_at
  return d ? new Date(d).toLocaleString('uk-UA') : '—'
})

const modifiedAt = computed(() => {
  const d = props.document.modified_at
  return d ? new Date(d).toLocaleString('uk-UA') : '—'
})

// Assignees
const assignees = ref<GruntDocument[]>([])
const assignLoading = ref(false)

async function loadAssignees() {
  assignLoading.value = true
  try {
    assignees.value = await docsApi.getAssignees(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { assignLoading.value = false }
}

// Shared with
const sharedWith = ref<GruntDocument[]>([])
const shareLoading = ref(false)

async function loadShared() {
  shareLoading.value = true
  try {
    sharedWith.value = await docsApi.getSharedWith(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { shareLoading.value = false }
}

// Backlinks
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

// Assign dialog (simple prompt for now)
async function handleAssign() {
  const user = window.prompt('Email користувача для призначення:')
  if (!user) return
  try {
    await docsApi.assign(props.doctype.name, props.document.id, user)
    await loadAssignees()
  } catch { /* silent */ }
}

async function handleShare() {
  const user = window.prompt('Email користувача для надання доступу:')
  if (!user) return
  try {
    await docsApi.share(props.doctype.name, props.document.id, user)
    await loadShared()
  } catch { /* silent */ }
}

onMounted(() => {
  loadAssignees()
  loadShared()
  loadLinks()
})
</script>

<template>
  <aside class="flex flex-col gap-5 w-full">
    <!-- Document image -->
    <div v-if="doctype.image_field" class="flex justify-center">
      <div
        v-if="imageUrl"
        class="size-28 rounded-xl overflow-hidden ring-1 ring-border/60 shadow-sm"
      >
        <img :src="imageUrl" :alt="document.name" class="size-full object-cover" />
      </div>
      <div
        v-else
        class="size-28 rounded-xl bg-muted/50 ring-1 ring-border/40 flex items-center justify-center"
      >
        <ImageIcon class="size-8 text-muted-foreground/40" />
      </div>
    </div>

    <!-- Actions: Assign + Share -->
    <div class="flex gap-2">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button variant="outline" size="sm" class="flex-1" @click="handleAssign">
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
            <Button variant="outline" size="sm" class="flex-1" @click="handleShare">
              <Share2 class="size-4 mr-1.5" />
              Поділитися
            </Button>
          </TooltipTrigger>
          <TooltipContent>Надати доступ до документа</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>

    <!-- Assignees list -->
    <div v-if="assignees.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Відповідальні</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="a in assignees" :key="a.id" variant="secondary" class="text-xs">
          {{ a.assigned_to }}
        </Badge>
      </div>
    </div>

    <!-- Shared with list -->
    <div v-if="sharedWith.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Доступ</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="s in sharedWith" :key="s.id" variant="outline" class="text-xs">
          {{ s.user }} · {{ s.permission }}
        </Badge>
      </div>
    </div>

    <!-- Meta information -->
    <div class="flex flex-col gap-3 text-sm">
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Інформація</span>
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
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <LinkIcon class="size-3.5 inline-block mr-1 -mt-0.5" />
        Зв'язки ({{ links.length }})
      </span>
      <button
        v-for="link in links"
        :key="`${link.source_doctype}-${link.source_id}`"
        class="flex items-center gap-2 text-sm text-foreground/80 hover:text-primary transition-colors group text-left"
        @click="navigateToLink(link)"
      >
        <ChevronRight class="size-3.5 text-muted-foreground/50 group-hover:text-primary transition-colors" />
        <span class="truncate">{{ link.source_doctype }}</span>
        <span class="text-xs text-muted-foreground truncate">{{ link.source_id.slice(0, 8) }}…</span>
      </button>
    </div>
  </aside>
</template>
