<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Share2, X, Loader2, ShieldCheck, User, Shield } from '@lucide/vue'
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
    <Tooltip>
      <TooltipTrigger as-child>
        <Button variant="outline" size="sm" class="w-full text-foreground shadow-sm transition-all active:scale-[0.98]" @click="showShareDialog = true">
          <Share2 class="size-3.5 mr-2" />
          <span class="text-xs font-semibold">{{ t('Share') }}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{{ t('Share document') }}</TooltipContent>
    </Tooltip>

    <div v-if="sharedWith.length > 0" class="flex flex-col gap-2 p-3 bg-muted/30 rounded-xl border border-border/40">
      <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">{{ t('Access') }}</span>
      <div class="flex flex-wrap gap-2">
        <Badge v-for="s in sharedWith" :key="s.id" 
          class="pl-1 pr-2 py-0.5 text-[11px] font-medium bg-background border border-border/60 shadow-sm"
        >
            <Avatar class="mr-2 !size-5">
              <AvatarFallback class="!text-[10px]" :class="s.permission === 'Write' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'"><Shield class="size-3.5" /></AvatarFallback>
            </Avatar>
            <span class="mr-2 truncate max-w-[120px]">{{ s.user }}</span>
            <span class="text-[9px] font-bold uppercase tracking-tighter text-muted-foreground/60 mr-2">{{ s.permission }}</span>
            <X class="size-3 cursor-pointer hover:text-destructive transition-colors" @click="removeShare(s)" />
        </Badge>
      </div>
    </div>

    <!-- Share dialog -->
    <Dialog v-model:open="showShareDialog">
      <DialogContent class="max-w-sm w-full mx-4 p-0 px-6 pb-6 pt-1">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2 font-bold text-lg">
          <Share2 class="size-5 text-primary" />
          {{ t('Share document') }}
        </DialogTitle>
      </DialogHeader>

      <div class="flex flex-col gap-5 py-2">
        <div class="flex flex-col gap-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Email або логін</label>
          <Input
            v-model="shareUser"
            placeholder="Пошук користувача..."
            class="w-full"
            @input="searchUsers(shareUser)"
          />
          <div v-if="filteredUsers.length" class="border border-border rounded-md overflow-hidden max-h-40 overflow-y-auto divide-y divide-border/60">
            <button
              v-for="u in filteredUsers"
              :key="u.email"
              type="button"
              class="w-full px-3 py-2 text-left hover:bg-primary/5 transition-colors flex items-center gap-2"
              @click="shareUser = u.email; filteredUsers = []"
            >
              <Avatar class="!size-6"><AvatarFallback><User class="size-3.5" /></AvatarFallback></Avatar>
              <div class="flex flex-col min-w-0">
                <span class="text-sm font-medium truncate">{{ u.full_name || u.email }}</span>
                <span class="text-[10px] text-muted-foreground truncate">{{ u.email }}</span>
              </div>
            </button>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Рівень доступу</label>
          <Select v-model="sharePermission">
            <SelectTrigger class="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in PERMISSION_OPTIONS" :key="opt.value" :value="opt.value">
                <div class="flex items-center gap-2">
                    <ShieldCheck v-if="opt.value === 'Write'" class="size-4 text-primary" />
                    <Share2 v-else class="size-4 text-muted-foreground" />
                    <span>{{ opt.label }}</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <DialogFooter>
        <div class="flex gap-2 w-full pt-2">
            <Button variant="outline" class="flex-1" @click="showShareDialog = false">{{ t('Cancel') }}</Button>
            <Button class="flex-1" :disabled="!shareUser.trim() || shareSaving" @click="submitShare">
                <Loader2 v-if="shareSaving" class="size-4 animate-spin mr-2" />
                <span v-else>{{ t('Grant access') }}</span>
            </Button>
        </div>
      </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
