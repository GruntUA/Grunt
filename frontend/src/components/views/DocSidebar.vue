<script setup lang="ts">
import { ref, computed, onMounted, useAttrs } from 'vue'
import type { DocType, GruntDocument } from '@/types'
import { docsApi, type BacklinkItem } from '@/core/api/docs'
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
  Tag,
  Plus,
  X,
  Loader2,
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
}>()

const router = useRouter()
const attrs = useAttrs()

defineOptions({ inheritAttrs: false })

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
  // prevent duplicate
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

onMounted(() => {
  loadAssignees()
  loadShared()
  loadTags()
  loadLinks()
})
</script>

<template>
  <aside v-bind="attrs" class="flex flex-col gap-5 w-full">
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
    </div>

    <!-- Assignees list -->
    <div v-if="assignees.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Відповідальні</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge
          v-for="a in assignees"
          :key="a.id"
          variant="secondary"
          class="text-xs gap-1 pr-1"
        >
          {{ a.assigned_to }}
          <button
            type="button"
            class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
            @click="removeAssignee(a)"
          >
            <X class="size-2.5" />
          </button>
        </Badge>
      </div>
    </div>

    <!-- Shared with list -->
    <div v-if="sharedWith.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Доступ</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge
          v-for="s in sharedWith"
          :key="s.id"
          variant="outline"
          class="text-xs gap-1 pr-1"
        >
          {{ s.user }} · {{ s.permission }}
          <button
            type="button"
            class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
            @click="removeShare(s)"
          >
            <X class="size-2.5" />
          </button>
        </Badge>
      </div>
    </div>

    <!-- Tags -->
    <div class="flex flex-col gap-2">
      <span class="text-xs font-medium uppercase tracking-wider text-muted-foreground flex items-center gap-1">
        <Tag class="size-3.5" />
        Теги
      </span>
      <div class="flex flex-wrap gap-1.5">
        <Badge
          v-for="t in tags"
          :key="t.id"
          variant="outline"
          class="text-xs gap-1 pr-1 text-foreground"
        >
          {{ t.tag }}
          <button
            type="button"
            class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
            @click="removeTag(t)"
          >
            <X class="size-2.5" />
          </button>
        </Badge>
      </div>
      <div class="flex gap-1.5">
        <input
          v-model="tagInput"
          placeholder="Додати тег..."
          class="flex-1 h-7 rounded-md border border-input bg-transparent px-2.5 text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
          @keydown="onTagKeydown"
        />
        <Button
          variant="outline"
          size="icon-sm"
          class="size-7 text-foreground shrink-0"
          :disabled="!tagInput.trim() || tagAdding"
          @click="addTag"
        >
          <Loader2 v-if="tagAdding" class="size-3.5 animate-spin" />
          <Plus v-else class="size-3.5" />
        </Button>
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
          <input
            v-model="assignUser"
            placeholder="user@example.com"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitAssign"
          />
        </div>
        <div v-if="assignees.length > 0" class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-muted-foreground">Вже призначені</span>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              v-for="a in assignees"
              :key="a.id"
              variant="secondary"
              class="text-xs gap-1 pr-1"
            >
              {{ a.assigned_to }}
              <button
                type="button"
                class="ml-0.5 rounded-full hover:bg-foreground/10 p-0.5"
                @click="removeAssignee(a)"
              >
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
          <input
            v-model="shareUser"
            placeholder="user@example.com"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitShare"
          />
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
            <div
              v-for="s in sharedWith"
              :key="s.id"
              class="flex items-center justify-between text-sm text-foreground"
            >
              <span>{{ s.user }}</span>
              <div class="flex items-center gap-2">
                <span class="text-xs text-muted-foreground">{{ s.permission === 'Read' ? 'Читання' : 'Редагування' }}</span>
                <button
                  type="button"
                  class="text-muted-foreground hover:text-destructive transition-colors"
                  @click="removeShare(s)"
                >
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
