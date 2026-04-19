<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const PERMISSION_OPTIONS = [
  { value: 'Read', label: 'Читання' },
  { value: 'Write', label: 'Редагування' },
]
import { Share2, X, Loader2 } from '@lucide/vue'
import { docsApi } from '@/core/api/docs'
import type { DocType, GruntDocument } from '@/types'

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

onMounted(loadShared)
</script>

<template>
  <div class="flex flex-col gap-3 mb-4">
    <Button v-tooltip="t('Share document')" outlined size="small" class="w-full text-foreground" @click="showShareDialog = true">
      <Share2 class="size-4 mr-1.5" />
      {{ t('Share') }}
    </Button>

    <div v-if="sharedWith.length > 0" class="flex flex-col gap-1.5">
      <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">{{ t('Access') }}</span>
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="s in sharedWith" :key="s.id" severity="contrast" class="text-xs gap-1 pr-1">
          {{ s.user }} · {{ s.permission }}
          <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
            @click="removeShare(s)">
            <X class="size-2.5" />
          </button>
        </Badge>
      </div>
    </div>

    <!-- Share dialog -->
    <Dialog v-model:visible="showShareDialog" modal
      :pt="{ root: { class: 'max-w-sm' }, content: { class: 'p-0 px-6 pb-4 pt-1' } }">
      <template #header>
        <span class="flex items-center gap-2 font-semibold">
          <Share2 class="size-4" />
          {{ t('Share document') }}
        </span>
      </template>
      <div class="flex flex-col gap-3 py-1">
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Email або логін</label>
          <input v-model="shareUser" placeholder="user@example.com"
            class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            @keydown.enter="submitShare" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-sm font-medium text-foreground">Рівень доступу</label>
          <Select
            v-model="sharePermission"
            :options="PERMISSION_OPTIONS"
            option-label="label"
            option-value="value"
            class="w-full"
          />
        </div>
      </div>
      <template #footer>
        <Button outlined class="text-foreground" @click="showShareDialog = false">{{ t('Cancel') }}</Button>
        <Button :disabled="!shareUser.trim() || shareSaving" @click="submitShare">
          <Loader2 v-if="shareSaving" class="size-4 animate-spin mr-1.5" />
          {{ t('Grant access') }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>
