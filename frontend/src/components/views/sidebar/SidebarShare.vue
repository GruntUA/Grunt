<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Share2, X, Loader2, ShieldCheck } from '@lucide/vue'
import { docsApi } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import type { DocType, GruntDocument, UserPublic } from '@/types'

const PERMISSION_OPTIONS = [
  { value: 'Read', label: 'Читання' },
  { value: 'Write', label: 'Редагування' },
]

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

const { t } = useI18n()
const sharedWith = ref<GruntDocument[]>([])
const shareLoading = ref(false)

async function loadShared() {
  shareLoading.value = true
  try {
    sharedWith.value = await docsApi.getSharedWith(props.doctype.name, props.document.name)
  } catch { /* silent */ }
  finally { shareLoading.value = false }
}

const showShareDialog = ref(false)
const shareUser = ref('')
const sharePermission = ref<'Read' | 'Write'>('Read')
const shareSaving = ref(false)

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

async function submitShare() {
  const user = shareUser.value.trim()
  if (!user) return
  shareSaving.value = true
  try {
    await docsApi.share(props.doctype.name, props.document.name, user, sharePermission.value)
    await loadShared()
    showShareDialog.value = false
    shareUser.value = ''
    sharePermission.value = 'Read'
  } catch { /* silent */ }
  finally { shareSaving.value = false }
}

async function removeShare(share: GruntDocument) {
  try {
    await docsApi.unshare(share.name)
    sharedWith.value = sharedWith.value.filter(s => s.id !== share.id)
  } catch { /* silent */ }
}

onMounted(loadShared)
</script>

<template>
  <div class="flex flex-col gap-3 mb-0">
    <Button v-tooltip="t('Share document')" outlined size="small" class="w-full text-foreground shadow-sm transition-all active:scale-[0.98]" @click="showShareDialog = true">
      <Share2 class="size-3.5 mr-2" />
      <span class="text-xs font-semibold">{{ t('Share') }}</span>
    </Button>

    <div v-if="sharedWith.length > 0" class="flex flex-col gap-2 p-3 bg-muted/30 rounded-xl border border-border/40">
      <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">{{ t('Access') }}</span>
      <div class="flex flex-wrap gap-2">
        <Chip v-for="s in sharedWith" :key="s.id" 
          class="pl-1 pr-2 py-0.5 text-[11px] font-medium bg-background border border-border/60 shadow-sm"
        >
            <Avatar icon="pi pi-shield" shape="circle" class="mr-2 !size-5 !text-[10px]" :class="s.permission === 'Write' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'" />
            <span class="mr-2 truncate max-w-[120px]">{{ s.user }}</span>
            <span class="text-[9px] font-bold uppercase tracking-tighter text-muted-foreground/60 mr-2">{{ s.permission }}</span>
            <X class="size-3 cursor-pointer hover:text-destructive transition-colors" @click="removeShare(s)" />
        </Chip>
      </div>
    </div>

    <!-- Share dialog -->
    <Dialog v-model:visible="showShareDialog" modal
      header="Поділитися документом"
      class="max-w-sm w-full mx-4"
      :pt="{ content: { class: 'p-0 px-6 pb-6 pt-1' } }">
      <template #header>
        <span class="flex items-center gap-2 font-bold text-lg">
          <Share2 class="size-5 text-primary" />
          {{ t('Share document') }}
        </span>
      </template>

      <div class="flex flex-col gap-5 py-2">
        <div class="flex flex-col gap-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Email або логін</label>
          <AutoComplete 
            v-model="shareUser" 
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

        <div class="flex flex-col gap-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Рівень доступу</label>
          <Select
            v-model="sharePermission"
            :options="PERMISSION_OPTIONS"
            option-label="label"
            option-value="value"
            class="w-full"
            fluid
          >
            <template #option="slotProps">
                <div class="flex items-center gap-2">
                    <ShieldCheck v-if="slotProps.option.value === 'Write'" class="size-4 text-primary" />
                    <Share2 v-else class="size-4 text-muted-foreground" />
                    <span>{{ slotProps.option.label }}</span>
                </div>
            </template>
          </Select>
        </div>
      </div>

      <template #footer>
        <div class="flex gap-2 w-full pt-2">
            <Button outlined severity="secondary" class="flex-1" @click="showShareDialog = false">{{ t('Cancel') }}</Button>
            <Button class="flex-1" :disabled="!shareUser.trim() || shareSaving" @click="submitShare">
                <Loader2 v-if="shareSaving" class="size-4 animate-spin mr-2" />
                <span v-else>{{ t('Grant access') }}</span>
            </Button>
        </div>
      </template>
    </Dialog>
  </div>
</template>
