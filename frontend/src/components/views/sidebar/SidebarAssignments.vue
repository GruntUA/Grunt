<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { UserPlus, X, Loader2 } from 'lucide-vue-next'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { docsApi } from '@/core/api/docs'
import type { DocType, GruntDocument } from '@/types'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

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
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger as-child>
          <Button variant="outline" size="sm" class="w-full text-foreground" @click="showAssignDialog = true">
            <UserPlus class="size-4 mr-1.5" />
            Призначити
          </Button>
        </TooltipTrigger>
        <TooltipContent>Призначити відповідальну особу</TooltipContent>
      </Tooltip>
    </TooltipProvider>

    <div v-if="assignees.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Відповідальні</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="a in assignees" :key="a.id" variant="secondary" class="text-xs gap-1 pr-1">
          {{ a.assigned_to }}
          <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
            @click="removeAssignee(a)">
            <X class="size-2.5" />
          </button>
        </Badge>
      </div>
    </div>

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
            <input v-model="assignUser" placeholder="user@example.com"
              class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
              @keydown.enter="submitAssign" />
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
  </div>
</template>
