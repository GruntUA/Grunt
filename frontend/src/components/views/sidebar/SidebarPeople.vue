<script setup lang="ts">
import { N_ } from '@/plugins/i18n'
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  CalendarClock,
  ChevronRight,
  Ellipsis,
  ExternalLink,
  NotebookPen,
  Plus,
  Share2,
  UserMinus,
  UserPlus,
  X,
} from '@lucide/vue'
import type { DocSidebarState } from './useDocSidebar'
import { isAssignmentPlaceholder, type SidebarAssignee } from '@/core/api/docs'
import { useDialog } from '@/core/composables/useDialog'
import { formatDate, formatRelative } from '@/core/datetime'
import { docUrl } from '@/core/workspaceUrl'
import SidebarUserCommand from './SidebarUserCommand.vue'
import SidebarPersonCard from './SidebarPersonCard.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CommandItem } from '@/components/ui/command'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<{ sb: DocSidebarState; workspace?: string }>()

const { t } = useI18n()
const router = useRouter()
const dialog = useDialog()

const assignees = computed(() => props.sb.bundle.value.assignees)
const shares = computed(() => props.sb.bundle.value.shares)

// ── Assignees ───────────────────────────────────────────────────────────────
// A ToDo created without a task text carries an auto-generated placeholder —
// treat that as "no text" so it's not shown as an actual task.
function realNote(a: SidebarAssignee): string {
  const d = (a.description ?? '').trim()
  return isAssignmentPlaceholder(d) ? '' : d
}
const STATUS_LABEL: Record<string, string> = { Open: N_('status|Open'), 'In Progress': N_('status|In Progress') }
function statusLabel(a: SidebarAssignee): string {
  return a.status ? (STATUS_LABEL[a.status] ? t(STATUS_LABEL[a.status]) : a.status) : ''
}
const PRIORITY_LABEL: Record<string, string> = { Urgent: N_('priority|Urgent'), High: N_('priority|High') }
function priorityTag(a: SidebarAssignee): string {
  return a.priority && a.priority in PRIORITY_LABEL ? t(PRIORITY_LABEL[a.priority]) : ''
}
function taskUrl(a: SidebarAssignee): string {
  return docUrl('ToDo', a.name, props.workspace)
}
function openTask(a: SidebarAssignee) {
  router.push(taskUrl(a))
}
function assignedMeta(a: SidebarAssignee): string | undefined {
  return a.created_at ? t('assigned {when}', { when: formatRelative(a.created_at) }) : undefined
}
async function confirmUnassign(a: SidebarAssignee) {
  const ok = await dialog.confirm(t('Remove {name} from assignees?', { name: props.sb.personName(a.assigned_to) }))
  if (ok) await props.sb.unassign(a.name)
}

const assignOpen = ref(false)
async function quickAssign(email: string) {
  assignOpen.value = false
  try {
    await props.sb.assign(email)
  } catch {
    /* silent */
  }
}

// "Assign with a task" — the user picker plus a task text.
const taskDialog = ref(false)
const taskUser = ref('')
const taskNote = ref('')
const taskSaving = ref(false)
function openTaskDialog() {
  assignOpen.value = false
  taskUser.value = ''
  taskNote.value = ''
  taskDialog.value = true
}
async function submitTask() {
  if (!taskUser.value) return
  taskSaving.value = true
  try {
    await props.sb.assign(taskUser.value, taskNote.value)
    taskDialog.value = false
  } catch {
    /* silent */
  } finally {
    taskSaving.value = false
  }
}

// ── Access ──────────────────────────────────────────────────────────────────
const shareOpen = ref(false)
const sharePermission = ref<'Read' | 'Write'>('Read')
const accessOpen = ref(false)
async function quickShare(email: string) {
  shareOpen.value = false
  try {
    await props.sb.share(email, sharePermission.value)
    accessOpen.value = true
  } catch {
    /* silent */
  }
}
function permissionLabel(p: string): string {
  return p === 'Write' ? t('Edit') : p === 'Read' ? t('Read') : p
}
</script>

<template>
  <!-- Assignees -->
  <section class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium">{{ t('Assignees') }}</h3>
      <Popover v-model:open="assignOpen">
        <PopoverTrigger as-child>
          <Button variant="ghost" size="icon-sm" class="size-7 -mr-1.5" :aria-label="t('Assign')">
            <UserPlus />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" class="w-64 p-0">
          <SidebarUserCommand v-if="assignOpen" :sb="sb" :exclude="assignees.map((a) => a.assigned_to)" @select="quickAssign">
            <template #footer>
              <CommandItem value="__with-task" @select="openTaskDialog">
                <NotebookPen class="size-4" />
                {{ t('Assign with a task…') }}
              </CommandItem>
            </template>
          </SidebarUserCommand>
        </PopoverContent>
      </Popover>
    </div>

    <ItemGroup v-if="assignees.length" class="-mx-2 gap-0.5">
      <!-- The title link stretches over the row; avatar and actions sit above it. -->
      <Item
        v-for="a in assignees"
        :key="a.name"
        size="sm"
        class="relative flex-nowrap items-start gap-2.5 px-2 py-1.5 hover:bg-accent/50"
      >
        <SidebarPersonCard :sb="sb" :email="a.assigned_to" :meta="assignedMeta(a)">
          <ItemMedia class="relative z-10">
            <Avatar
              class="size-7 ring-2"
              :class="a.is_overdue ? 'ring-destructive/50' : a.status === 'In Progress' ? 'ring-primary/50' : 'ring-transparent'"
            >
              <AvatarImage v-if="sb.personAvatar(a.assigned_to)" :src="sb.personAvatar(a.assigned_to)!" />
              <AvatarFallback class="text-[10px]">{{ sb.personInitials(a.assigned_to) }}</AvatarFallback>
            </Avatar>
          </ItemMedia>
        </SidebarPersonCard>
        <ItemContent class="min-w-0 gap-1">
          <ItemTitle class="w-full">
            <RouterLink
              :to="taskUrl(a)"
              class="truncate outline-none after:absolute after:inset-0 after:rounded-md focus-visible:after:ring-3 focus-visible:after:ring-ring/50"
            >
              {{ sb.personName(a.assigned_to) }}
            </RouterLink>
          </ItemTitle>
          <ItemDescription v-if="realNote(a)" class="text-xs">{{ realNote(a) }}</ItemDescription>
          <div class="flex flex-wrap gap-1">
            <Badge v-if="statusLabel(a)" :variant="a.status === 'In Progress' ? 'secondary' : 'outline'" class="font-normal">
              {{ statusLabel(a) }}
            </Badge>
            <Badge v-if="a.due_date" :variant="a.is_overdue ? 'destructive' : 'outline'" class="font-normal">
              <CalendarClock />
              {{ formatDate(a.due_date) }}
            </Badge>
            <Badge v-if="priorityTag(a)" variant="outline" class="font-normal">{{ priorityTag(a) }}</Badge>
          </div>
        </ItemContent>
        <ItemActions class="relative z-10">
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button variant="ghost" size="icon-xs" :aria-label="t('More actions')">
                <Ellipsis />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem @select="openTask(a)">
                <ExternalLink />
                {{ t('Open task') }}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" @select="confirmUnassign(a)">
                <UserMinus />
                {{ t('Unassign') }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </ItemActions>
      </Item>
    </ItemGroup>
    <p v-else class="text-sm text-muted-foreground">{{ t('Nobody is assigned') }}</p>
  </section>

  <!-- Access -->
  <Collapsible v-model:open="accessOpen" as="section" class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <CollapsibleTrigger
        v-if="shares.length"
        class="group -ml-1 flex items-center gap-1 rounded-sm px-1 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <ChevronRight class="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        {{ t('Access') }}
        <Badge variant="secondary" class="px-1.5 font-normal tabular-nums">{{ shares.length }}</Badge>
      </CollapsibleTrigger>
      <h3 v-else class="text-sm font-medium">{{ t('Access') }}</h3>
      <Popover v-model:open="shareOpen">
        <PopoverTrigger as-child>
          <Button variant="ghost" size="icon-sm" class="size-7 -mr-1.5" :aria-label="t('Share document')">
            <Share2 />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" class="w-64 p-0">
          <div class="border-b p-2">
            <ToggleGroup
              :model-value="sharePermission"
              type="single"
              variant="outline"
              size="sm"
              class="w-full"
              @update:model-value="(v) => { if (v) sharePermission = v as 'Read' | 'Write' }"
            >
              <ToggleGroupItem value="Read" class="flex-1">{{ t('Read') }}</ToggleGroupItem>
              <ToggleGroupItem value="Write" class="flex-1">{{ t('Edit') }}</ToggleGroupItem>
            </ToggleGroup>
          </div>
          <SidebarUserCommand v-if="shareOpen" :sb="sb" :exclude="shares.map((s) => s.user)" @select="quickShare" />
        </PopoverContent>
      </Popover>
    </div>
    <CollapsibleContent v-if="shares.length">
      <ItemGroup class="-mx-2">
        <Item v-for="s in shares" :key="s.name" size="sm" class="flex-nowrap gap-2 px-2 py-1">
          <SidebarPersonCard :sb="sb" :email="s.user">
            <ItemMedia>
              <Avatar class="size-6">
                <AvatarImage v-if="sb.personAvatar(s.user)" :src="sb.personAvatar(s.user)!" />
                <AvatarFallback class="text-[9px]">{{ sb.personInitials(s.user) }}</AvatarFallback>
              </Avatar>
            </ItemMedia>
          </SidebarPersonCard>
          <ItemContent class="min-w-0">
            <ItemTitle class="w-full font-normal">
              <span class="truncate">{{ sb.personName(s.user) }}</span>
            </ItemTitle>
          </ItemContent>
          <ItemActions class="gap-1">
            <Badge variant="outline" class="font-normal">{{ permissionLabel(s.permission) }}</Badge>
            <Button
              variant="ghost"
              size="icon-xs"
              class="text-muted-foreground hover:text-destructive"
              :aria-label="t('Remove {name}', { name: sb.personName(s.user) })"
              @click="sb.unshare(s.name)"
            >
              <X />
            </Button>
          </ItemActions>
        </Item>
      </ItemGroup>
    </CollapsibleContent>
    <p v-else class="text-sm text-muted-foreground">{{ t('Not shared with anyone') }}</p>
  </Collapsible>

  <!-- Assign with a task -->
  <Dialog v-model:open="taskDialog">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ t('Assign with a task') }}</DialogTitle>
        <DialogDescription>{{ t('The assignee gets a task linked to this document.') }}</DialogDescription>
      </DialogHeader>

      <FieldGroup>
        <Field>
          <FieldLabel>{{ t('Assignee') }}</FieldLabel>
          <div class="rounded-md border">
            <SidebarUserCommand v-if="!taskUser" :sb="sb" @select="taskUser = $event" />
            <Item v-else size="sm" class="flex-nowrap gap-2 px-2 py-1.5">
              <ItemMedia>
                <Avatar class="size-6">
                  <AvatarImage v-if="sb.personAvatar(taskUser)" :src="sb.personAvatar(taskUser)!" />
                  <AvatarFallback class="text-[10px]">{{ sb.personInitials(taskUser) }}</AvatarFallback>
                </Avatar>
              </ItemMedia>
              <ItemContent class="min-w-0">
                <ItemTitle class="w-full font-normal"><span class="truncate">{{ sb.personName(taskUser) }}</span></ItemTitle>
              </ItemContent>
              <ItemActions>
                <Button variant="ghost" size="icon-xs" :aria-label="t('Change')" @click="taskUser = ''">
                  <X />
                </Button>
              </ItemActions>
            </Item>
          </div>
        </Field>
        <Field>
          <FieldLabel for="sidebar-task-note">{{ t('Task text') }}</FieldLabel>
          <Textarea
            id="sidebar-task-note"
            v-model="taskNote"
            rows="3"
            :placeholder="t('What needs to be done?')"
            class="resize-none"
          />
          <FieldDescription>{{ t('Optional. Without it the task only links to the document.') }}</FieldDescription>
        </Field>
      </FieldGroup>

      <DialogFooter>
        <Button variant="outline" @click="taskDialog = false">{{ t('Cancel') }}</Button>
        <Button :disabled="!taskUser || taskSaving" @click="submitTask">
          <Spinner v-if="taskSaving" />
          <Plus v-else />
          {{ t('Assign') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
