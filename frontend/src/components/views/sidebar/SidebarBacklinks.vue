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
    ? `/${props.workspace}/${link.source_doctype}/${link.source_id}`
    : `/${link.source_doctype}/${link.source_id}`
  router.push(path)
}

onMounted(loadLinks)
</script>

<template>
  <div v-if="links.length > 0" class="flex flex-col gap-3 p-3 bg-muted/30 rounded-xl border border-border/40">
    <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5 px-0.5">
      <LinkIcon class="size-3" />
      Зв'язки ({{ links.length }})
    </span>
    <div class="flex flex-col gap-1.5">
        <button v-for="link in links" :key="`${link.source_doctype}-${link.source_id}`"
            class="flex items-center gap-2 p-2 rounded-lg bg-background border border-border/40 hover:border-primary/50 hover:bg-primary/5 transition-all group text-left shadow-sm active:scale-[0.98]"
            @click="navigateToLink(link)">
            <ChevronRight class="size-3 text-muted-foreground/50 group-hover:text-primary transition-colors" />
            <div class="flex flex-col min-w-0">
                <span class="text-xs font-bold text-foreground truncate">{{ link.source_doctype }}</span>
                <span class="text-[10px] text-muted-foreground truncate">{{ link.source_id }}</span>
            </div>
        </button>
    </div>
  </div>
</template>
