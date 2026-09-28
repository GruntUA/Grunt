<script setup lang="ts">
import { useI18n } from 'vue-i18n'
/**
 * Frappe-style "Links" dialog: documents that reference this one (DocLink
 * backlinks), grouped by source DocType. Opened from the form "⋯" menu;
 * the list is fetched on open.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Loader2 } from '@lucide/vue'
import { docsApi, type BacklinkItem } from '@/core/api/docs'
import { useDocTypeStore } from '@/stores/doctype'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { docUrl } from '@/core/workspaceUrl'
import { Input } from '@/components/ui/input'

const { t } = useI18n()

const props = defineProps<{
  doctype: string
  docId: string
  workspace?: string
}>()
const open = defineModel<boolean>('open', { default: false })

const router = useRouter()
const dtStore = useDocTypeStore()
const links = ref<BacklinkItem[]>([])
const loading = ref(false)
const query = ref('')

watch(open, async (v) => {
  if (!v) return
  query.value = ''
  loading.value = true
  try {
    links.value = await docsApi.getLinks(props.doctype, props.docId)
  } catch {
    links.value = []
  } finally {
    loading.value = false
  }
  // Resolve human labels for the group headers; unknown/forbidden DocTypes keep their name.
  for (const name of new Set(links.value.map((l) => l.source_doctype))) {
    dtStore.get(name).catch(() => {})
  }
})

function doctypeLabel(name: string): string {
  return dtStore.cache.get(name)?.label || name
}

const groups = computed(() => {
  const q = query.value.trim().toLowerCase()
  const byDoctype = new Map<string, BacklinkItem[]>()
  for (const l of links.value) {
    if (q && ![l.title, l.source_id, doctypeLabel(l.source_doctype)].some((s) => s.toLowerCase().includes(q))) continue
    const items = byDoctype.get(l.source_doctype) ?? []
    items.push(l)
    byDoctype.set(l.source_doctype, items)
  }
  return [...byDoctype].map(([doctype, items]) => ({ doctype, items }))
})

function goTo(l: BacklinkItem) {
  open.value = false
  router.push(docUrl(l.source_doctype, l.source_id, props.workspace))
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-xl max-h-[85vh] flex flex-col">
      <DialogHeader>
        <DialogTitle>{{ t('Connections') }}</DialogTitle>
        <DialogDescription>
          {{ t('Documents linked to') }} <span class="font-semibold text-foreground">{{ docId }}</span>
        </DialogDescription>
      </DialogHeader>

      <Input v-if="links.length > 10" v-model="query" :placeholder="t('Search...')" />

      <div class="flex flex-col gap-3 min-h-0 overflow-y-auto -mx-6 px-6">
        <Loader2 v-if="loading" class="size-5 animate-spin text-muted-foreground mx-auto my-6" />
        <template v-else>
          <div v-for="g in groups" :key="g.doctype" class="shrink-0 rounded-md border">
            <div class="flex items-center justify-between px-3 py-1.5 rounded-t-md bg-muted text-muted-foreground">
              <span>{{ doctypeLabel(g.doctype) }}</span>
              <span class="tabular-nums">{{ g.items.length }}</span>
            </div>
            <button
              v-for="l in g.items"
              :key="`${l.source_id}-${l.link_fieldname}`"
              type="button"
              class="w-full flex items-baseline gap-3 text-left px-3 py-2 border-t hover:bg-accent transition-colors last:rounded-b-md"
              @click="goTo(l)"
            >
              <span class="font-medium truncate">{{ l.title }}</span>
              <span v-if="l.title !== l.source_id" class="ml-auto shrink-0 font-mono text-muted-foreground">{{ l.source_id }}</span>
            </button>
          </div>
          <span v-if="!groups.length" class="text-muted-foreground py-6 text-center">
            {{ links.length ? t('Nothing found') : t('No linked documents') }}
          </span>
        </template>
      </div>
    </DialogContent>
  </Dialog>
</template>
