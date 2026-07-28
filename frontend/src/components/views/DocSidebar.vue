<script setup lang="ts">
import { ref, useAttrs } from 'vue'
import type { DocType, GruntDocument } from '@/types'
import { docsApi } from '@/core/api/docs'
import {
  User,
  Bookmark,
} from '@lucide/vue'
import type { PresenceUser } from '@/core/composables/usePresence'

// Sub-components
import SidebarFileInfo from './sidebar/SidebarFileInfo.vue'
import SidebarAssignments from './sidebar/SidebarAssignments.vue'
import SidebarShare from './sidebar/SidebarShare.vue'
import SidebarTags from './sidebar/SidebarTags.vue'
import SidebarBacklinks from './sidebar/SidebarBacklinks.vue'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
}>()

const attrs = useAttrs()
defineOptions({ inheritAttrs: false })

// ── Bookmark ──────────────────────────────────────────────────────────────────
const bookmark = ref<GruntDocument | null>(null)
const bookmarkLoading = ref(false)

async function loadBookmark() {
  try {
    const doctypeName = props.doctype.name
    if (doctypeName && props.document.id) {
      bookmark.value = await docsApi.getBookmark(doctypeName, props.document.name)
    }
  } catch { /* silent */ }
}

async function toggleBookmark() {
  bookmarkLoading.value = true
  try {
    if (bookmark.value) {
      await docsApi.removeBookmark(props.doctype.name, props.document.name)
      bookmark.value = null
    } else {
      const title = String(props.document[props.doctype.title_field ?? 'name'] ?? props.document.name)
      bookmark.value = await docsApi.addBookmark(props.doctype.name, props.document.name, title)
    }
  } catch { /* silent */ }
  finally { bookmarkLoading.value = false }
}

// Initial load
loadBookmark()
</script>

<template>
  <aside v-bind="attrs" class="flex flex-col gap-0 w-full">
    <div class="form-section bg-card border border-border/60 rounded-xl shadow-sm overflow-hidden">
      <div class="form-section-header border-b border-border/60 px-4 py-3">
        <User class="size-3.5 text-muted-foreground" />
        <span class="text-[11px] font-bold uppercase tracking-wider">Деталі</span>
      </div>
      <div class="form-section-body p-4 flex flex-col gap-5">
        <SidebarFileInfo :doctype="doctype" :document="document" :users="users" />

        <div class="flex gap-2">
          <SidebarAssignments :doctype="doctype" :document="document" class="flex-1 mb-0" />
          <SidebarShare :doctype="doctype" :document="document" class="flex-1 mb-0" />
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="outline"
                :class="['size-9 shrink-0 shadow-sm transition-all active:scale-95', bookmark ? 'text-warning border-warning/40' : '']"
                :disabled="bookmarkLoading"
                @click="toggleBookmark"
              >
                <Bookmark class="size-4" :fill="bookmark ? 'currentColor' : 'none'" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{{ bookmark ? 'Прибрати із закладок' : 'Додати до закладок' }}</TooltipContent>
          </Tooltip>
        </div>

        <SidebarTags :doctype="doctype" :document="document" />
        <SidebarBacklinks :doctype="doctype" :document="document" :workspace="workspace" />
      </div>
    </div>
  </aside>
</template>
