<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { UserPlus, X, Loader2, User } from '@lucide/vue'
import { docsApi } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import type { DocType, GruntDocument, UserPublic } from '@/types'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

const { t } = useI18n()
const assignees = ref<GruntDocument[]>([])
const assignLoading = ref(false)

async function loadAssignees() {
  assignLoading.value = true
  try {
    assignees.value = await docsApi.getAssignees(props.doctype.name, props.document.name)
  } catch { /* silent */ }
  finally { assignLoading.value = false }
}

const showAssignDialog = ref(false)
const assignUser = ref<any>('')
const assignSaving = ref(false)

function getAssignEmail(): string {
  const v = assignUser.value
  if (!v) return ''
  return typeof v === 'object' ? (v.email ?? '') : String(v)
}

// User search
const users = ref<UserPublic[]>([])
const filteredUsers = ref<UserPublic[]>([])

async function searchUsers(query: string) {
    if (users.value.length === 0) {
        try { users.value = await authAdminApi.listUsers() } catch { return }
    }
    if (!query) { filteredUsers.value = []; return }
    const q = query.toLowerCase()
    filteredUsers.value = users.value.filter(u =>
        u.email.toLowerCase().includes(q) ||
        (u.full_name && u.full_name.toLowerCase().includes(q))
    )
}

async function submitAssign() {
  const user = getAssignEmail().trim()
  if (!user) return
  assignSaving.value = true
  try {
    await docsApi.assign(props.doctype.name, props.document.name, user)
    await loadAssignees()
    showAssignDialog.value = false
    assignUser.value = ''
  } catch { /* silent */ }
  finally { assignSaving.value = false }
}

async function removeAssignee(assignee: GruntDocument) {
  try {
    await docsApi.unassign(assignee.name)
    assignees.value = assignees.value.filter(a => a.name !== assignee.name)
  } catch { /* silent */ }
}

onMounted(loadAssignees)
</script>

<template>
  <div class="flex flex-col gap-3 mb-0">
    <Tooltip>
      <TooltipTrigger as-child>
        <Button variant="outline" size="sm" class="w-full text-foreground shadow-sm transition-all active:scale-[0.98]" @click="showAssignDialog = true">
          <UserPlus class="size-3.5 mr-2" />
          <span class="text-xs font-semibold">{{ t('Assign') }}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{{ t('Assign responsible person') }}</TooltipContent>
    </Tooltip>

    <div v-if="assignees.length > 0" class="flex flex-col gap-2 p-3 bg-muted/30 rounded-xl border border-border/40">
      <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">{{ t('Assignees') }}</span>
      <div class="flex flex-wrap gap-2">
        <Badge v-for="a in assignees" :key="a.id" 
          class="pl-1 pr-2 py-0.5 text-[11px] font-medium bg-background border border-border/60 shadow-sm"
        >
            <Avatar class="mr-2 !size-5"><AvatarFallback class="!text-[10px]"><User class="size-3.5" /></AvatarFallback></Avatar>
            <span class="mr-2 truncate max-w-[120px]">{{ a.assigned_to }}</span>
            <X class="size-3 cursor-pointer hover:text-destructive transition-colors" @click="removeAssignee(a)" />
        </Badge>
      </div>
    </div>

    <!-- Assign dialog -->
    <Dialog v-model:open="showAssignDialog">
      <DialogContent class="max-w-sm w-full mx-4 p-0 px-6 pb-6 pt-1">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2 font-bold text-lg">
          <UserPlus class="size-5 text-primary" />
          {{ t('Assign responsible') }}
        </DialogTitle>
      </DialogHeader>

      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Email або логін</label>
          <Input
            v-model="assignUser"
            placeholder="Пошук користувача..."
            class="w-full"
            @input="searchUsers(assignUser)"
          />
          <div v-if="filteredUsers.length" class="border border-border rounded-md overflow-hidden max-h-40 overflow-y-auto divide-y divide-border/60">
            <button
              v-for="u in filteredUsers"
              :key="u.email"
              type="button"
              class="w-full px-3 py-2 text-left hover:bg-primary/5 transition-colors flex items-center gap-2"
              @click="assignUser = u.email; filteredUsers = []"
            >
              <Avatar class="!size-6"><AvatarFallback><User class="size-3.5" /></AvatarFallback></Avatar>
              <div class="flex flex-col min-w-0">
                <span class="text-sm font-medium truncate">{{ u.full_name || u.email }}</span>
                <span class="text-[10px] text-muted-foreground truncate">{{ u.email }}</span>
              </div>
            </button>
          </div>
        </div>
      </div>

      <DialogFooter>
        <div class="flex gap-2 w-full pt-2">
            <Button variant="outline" class="flex-1" @click="showAssignDialog = false">{{ t('Cancel') }}</Button>
            <Button class="flex-1" :disabled="!getAssignEmail().trim() || assignSaving" @click="submitAssign">
                <Loader2 v-if="assignSaving" class="size-4 animate-spin mr-2" />
                <span v-else>{{ t('Assign') }}</span>
            </Button>
        </div>
      </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
