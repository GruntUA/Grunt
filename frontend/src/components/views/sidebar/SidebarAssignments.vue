<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { UserPlus, X, Loader2 } from '@lucide/vue'
import { docsApi } from '@/core/api/docs'
import type { DocType, GruntDocument } from '@/types'

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
  <div class="flex flex-col gap-3 mb-4">
    <Button v-tooltip="t('Assign responsible person')" outlined size="small" class="w-full text-foreground" @click="showAssignDialog = true">
      <UserPlus class="size-4 mr-1.5" />
      {{ t('Assign') }}
    </Button>

    <div v-if="assignees.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">{{ t('Assignees') }}</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="a in assignees" :key="a.id" severity="secondary" class="text-xs gap-1 pr-1">
          {{ a.assigned_to }}
          <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
            @click="removeAssignee(a)">
            <X class="size-2.5" />
          </button>
        </Badge>
      </div>
    </div>

    <!-- Assign dialog -->
    <Dialog v-model:visible="showAssignDialog" modal
      :pt="{ root: { class: 'max-w-sm' }, content: { class: 'p-0 px-6 pb-4 pt-1' } }">
      <template #header>
        <span class="flex items-center gap-2 font-semibold">
          <UserPlus class="size-4" />
          {{ t('Assign responsible') }}
        </span>
      </template>
      <div class="flex flex-col gap-3 py-1">
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Email або логін</label>
          <input v-model="assignUser" placeholder="user@example.com"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitAssign" />
        </div>
      </div>
      <template #footer>
        <Button outlined class="text-foreground" @click="showAssignDialog = false">{{ t('Cancel') }}</Button>
        <Button :disabled="!assignUser.trim() || assignSaving" @click="submitAssign">
          <Loader2 v-if="assignSaving" class="size-4 animate-spin mr-1.5" />
          {{ t('Assign') }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>
