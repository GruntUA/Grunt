<script setup lang="ts">
import { ref, useAttrs } from 'vue'
import type { DocType, GruntDocument } from '@/types'
import { docsApi } from '@/core/api/docs'
import {
  User,
  Activity,
  Bookmark,
} from '@lucide/vue'
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
    <div class="form-section mb-0! border-0 bg-transparent shadow-none">
      <Tabs v-model:value="activeTab" class="w-full">
        <!-- Tab nav as section header -->
        <TabList scrollable variant="underline" class="w-full h-auto border-b border-border/60 bg-card rounded-t-xl px-2">
          <Tab value="details" variant="underline" class="flex items-center gap-1.5 px-4 py-3 h-11">
            <User class="size-3.5" />
            <span class="text-[11px] font-bold uppercase tracking-wider">Деталі</span>
          </Tab>
          <Tab value="timeline" variant="underline" class="flex items-center gap-1.5 px-4 py-3 h-11">
            <Activity class="size-3.5" />
            <span class="text-[11px] font-bold uppercase tracking-wider">Активність</span>
          </Tab>
        </TabList>

        <!-- Content -->
        <TabPanels class="p-0 bg-card border border-t-0 border-border/60 rounded-b-xl shadow-sm overflow-hidden">
          <div class="form-section-body p-4!">
            <TabPanel value="details" class="flex flex-col gap-5 focus:outline-none focus:ring-0">
              <SidebarFileInfo :doctype="doctype" :document="document" :users="users" />

              <!-- Actions -->
              <div class="flex gap-2">
                <SidebarAssignments :doctype="doctype" :document="document" class="flex-1 mb-0" />
                <SidebarShare :doctype="doctype" :document="document" class="flex-1 mb-0" />
                <Button v-tooltip="bookmark ? 'Прибрати із закладок' : 'Додати до закладок'"
                  outlined class="size-9 shrink-0 shadow-sm transition-all active:scale-95"
                  :severity="bookmark ? 'warn' : 'secondary'"
                  :disabled="bookmarkLoading"
                  @click="toggleBookmark"
                >
                  <Bookmark class="size-4" :fill="bookmark ? 'currentColor' : 'none'" />
                </Button>
              </div>

              <SidebarTags :doctype="doctype" :document="document" />
              <SidebarBacklinks :doctype="doctype" :document="document" :workspace="workspace" />
            </TabPanel>

            <TabPanel value="timeline" class="px-4! focus:outline-none focus:ring-0">
              <SidebarTimeline :doctype="doctype" :document="document" />
            </TabPanel>
          </div>
        </TabPanels>
      </Tabs>
    </div>
  </aside>
</template>
