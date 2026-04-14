<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Link as LinkIcon, ChevronRight } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { docsApi, type BacklinkItem } from '@/core/api/docs'
import type { DocType, GruntDocument } from '@/types'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
}>()

const router = useRouter()
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

onMounted(loadLinks)
</script>

<template>
  <div v-if="links.length > 0" class="flex flex-col gap-2">
    <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">
      <LinkIcon class="size-3.5 inline-block mr-1 -mt-0.5" />
      Зв'язки ({{ links.length }})
    </span>
    <button v-for="link in links" :key="`${link.source_doctype}-${link.source_id}`"
      class="flex items-center gap-2 text-sm text-foreground/80 hover:text-primary transition-colors group text-left"
      @click="navigateToLink(link)">
      <ChevronRight class="size-3.5 text-muted-foreground/50 group-hover:text-primary transition-colors" />
      <span class="truncate">{{ link.source_doctype }}</span>
      <span class="text-xs text-muted-foreground truncate">{{ link.source_id.slice(0, 8) }}…</span>
    </button>
  </div>
</template>
