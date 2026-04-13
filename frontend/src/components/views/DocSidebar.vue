<script setup lang="ts">
import { ref, useAttrs } from 'vue'
import type { DocType, GruntDocument } from '@/types'
import { docsApi } from '@/core/api/docs'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  User,
  Activity,
  Bookmark,
} from 'lucide-vue-next'
import type { PresenceUser } from '@/core/composables/usePresence'

// Sub-components
import SidebarFileInfo from './sidebar/SidebarFileInfo.vue'
import SidebarAssignments from './sidebar/SidebarAssignments.vue'
import SidebarShare from './sidebar/SidebarShare.vue'
import SidebarTags from './sidebar/SidebarTags.vue'
import SidebarBacklinks from './sidebar/SidebarBacklinks.vue'
import SidebarTimeline from './sidebar/SidebarTimeline.vue'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
}>()

const attrs = useAttrs()
defineOptions({ inheritAttrs: false })

// ── Tabs ──────────────────────────────────────────────────────────────────────
const activeTab = ref<'details' | 'timeline'>('details')

// ── Bookmark ──────────────────────────────────────────────────────────────────
const bookmark = ref<GruntDocument | null>(null)
const bookmarkLoading = ref(false)

async function loadBookmark() {
  try {
    bookmark.value = await docsApi.getBookmark(props.doctype.name, props.document.id)
  } catch { /* silent */ }
}

async function toggleBookmark() {
  bookmarkLoading.value = true
  try {
    if (bookmark.value) {
      await docsApi.removeBookmark(props.doctype.name, props.document.id)
      bookmark.value = null
    } else {
      const title = String(props.document[props.doctype.title_field ?? 'name'] ?? props.document.id)
      bookmark.value = await docsApi.addBookmark(props.doctype.name, props.document.id, title)
    }
  } catch { /* silent */ }
  finally { bookmarkLoading.value = false }
}

// Initial load
loadBookmark()
</script>

<template>
  <aside v-bind="attrs" class="flex flex-col gap-0 w-full">
    <div class="form-section">
      <!-- Tab nav as section header -->
      <div class="flex border-b border-border bg-muted/50">
        <button
          class="flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider border-b-2 transition-colors"
          :class="activeTab === 'details' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'"
          @click="activeTab = 'details'"
        >
          <User class="size-3.5" />
          Деталі
        </button>
        <button
          class="flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider border-b-2 transition-colors"
          :class="activeTab === 'timeline' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'"
          @click="activeTab = 'timeline'"
        >
          <Activity class="size-3.5" />
          Активність
        </button>
      </div>

      <!-- Content -->
      <div class="form-section-body">
        <!-- ── DETAILS TAB ── -->
        <div v-if="activeTab === 'details'" class="flex flex-col gap-4">
          <SidebarFileInfo :doctype="doctype" :document="document" :users="users" />

          <!-- Actions -->
          <div class="flex gap-2">
            <SidebarAssignments :doctype="doctype" :document="document" class="flex-1 mb-0" />
            <SidebarShare :doctype="doctype" :document="document" class="flex-1 mb-0" />
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="outline" size="icon" class="size-9 shrink-0"
                    :class="bookmark ? 'text-amber-500 border-amber-300 bg-amber-50 dark:bg-amber-950/30' : 'text-foreground'"
                    :disabled="bookmarkLoading"
                    @click="toggleBookmark">
                    <Bookmark class="size-4" :fill="bookmark ? 'currentColor' : 'none'" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{{ bookmark ? 'Прибрати із закладок' : 'Додати до закладок' }}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          <SidebarTags :doctype="doctype" :document="document" />
          <SidebarBacklinks :doctype="doctype" :document="document" :workspace="workspace" />
        </div>

        <!-- ── TIMELINE TAB ── -->
        <div v-else>
          <SidebarTimeline :doctype="doctype" :document="document" />
        </div>
      </div>
    </div>
  </aside>
</template>
