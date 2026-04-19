<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { UserPlus, X, Loader2 } from '@lucide/vue'
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
    assignees.value = await docsApi.getAssignees(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { assignLoading.value = false }
}

const showAssignDialog = ref(false)
const assignUser = ref('')
const assignSaving = ref(false)

// User search
const users = ref<UserPublic[]>([])
const filteredUsers = ref<UserPublic[]>([])

async function searchUsers(event: any) {
    if (users.value.length === 0) {
        try { users.value = await authAdminApi.listUsers() } catch { return }
    }
    const query = event.query.toLowerCase()
    filteredUsers.value = users.value.filter(u => 
        u.email.toLowerCase().includes(query) || 
        (u.full_name && u.full_name.toLowerCase().includes(query))
    )
}

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

onMounted(loadAssignees)
</script>

<template>
  <div class="flex flex-col gap-3 mb-0">
    <Button v-tooltip="t('Assign responsible person')" outlined size="small" class="w-full text-foreground shadow-sm transition-all active:scale-[0.98]" @click="showAssignDialog = true">
      <UserPlus class="size-3.5 mr-2" />
      <span class="text-xs font-semibold">{{ t('Assign') }}</span>
    </Button>

    <div v-if="assignees.length > 0" class="flex flex-col gap-2 p-3 bg-muted/30 rounded-xl border border-border/40">
      <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">{{ t('Assignees') }}</span>
      <div class="flex flex-wrap gap-2">
        <Chip v-for="a in assignees" :key="a.id" 
          class="pl-1 pr-2 py-0.5 text-[11px] font-medium bg-background border border-border/60 shadow-sm"
        >
            <Avatar icon="pi pi-user" shape="circle" class="mr-2 !size-5 !text-[10px]" />
            <span class="mr-2 truncate max-w-[120px]">{{ a.assigned_to }}</span>
            <X class="size-3 cursor-pointer hover:text-destructive transition-colors" @click="removeAssignee(a)" />
        </Chip>
      </div>
    </div>

    <!-- Assign dialog -->
    <Dialog v-model:visible="showAssignDialog" modal
      header="Призначити відповідального"
      class="max-w-sm w-full mx-4"
      :pt="{ content: { class: 'p-0 px-6 pb-6 pt-1' } }">
      <template #header>
        <span class="flex items-center gap-2 font-bold text-lg">
          <UserPlus class="size-5 text-primary" />
          {{ t('Assign responsible') }}
        </span>
      </template>
      
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Email або логін</label>
          <AutoComplete 
            v-model="assignUser" 
            :suggestions="filteredUsers" 
            optionLabel="email"
            optionValue="email"
            @complete="searchUsers"
            placeholder="Пошук користувача..." 
            class="w-full"
            fluid
          >
            <template #option="slotProps">
                <div class="flex items-center gap-2">
                    <Avatar icon="pi pi-user" shape="circle" class="!size-6" />
                    <div class="flex flex-col">
                        <span class="text-sm font-medium">{{ slotProps.option.full_name || slotProps.option.email }}</span>
                        <span class="text-[10px] text-muted-foreground">{{ slotProps.option.email }}</span>
                    </div>
                </div>
            </template>
          </AutoComplete>
        </div>
      </div>

      <template #footer>
        <div class="flex gap-2 w-full pt-2">
            <Button outlined severity="secondary" class="flex-1" @click="showAssignDialog = false">{{ t('Cancel') }}</Button>
            <Button class="flex-1" :disabled="!assignUser.trim() || assignSaving" @click="submitAssign">
                <Loader2 v-if="assignSaving" class="size-4 animate-spin mr-2" />
                <span v-else>{{ t('Assign') }}</span>
            </Button>
        </div>
      </template>
    </Dialog>
  </div>
</template>
