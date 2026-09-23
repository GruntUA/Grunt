<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { workspaceApi, type MyWork } from '@/core/api/workspace'
import { isAssignmentPlaceholder } from '@/core/api/docs'
import { CheckSquare, Bell } from '@lucide/vue'
import { formatIntl } from '@/core/datetime'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { docUrl } from '@/core/workspaceUrl'

const router = useRouter()

const data = ref<MyWork | null>(null)
const loading = ref(true)

const assignedCount = computed(() => data.value?.counts.assigned ?? 0)
const unreadCount = computed(() => data.value?.counts.unread ?? 0)

// The task text, unless it's the auto-generated assignment placeholder.
function taskNote(t: MyWork['assigned'][number]): string {
  const d = (t.description ?? '').trim()
  return isAssignmentPlaceholder(d) ? '' : d
}

function openTask(t: MyWork['assigned'][number]) {
  if (!t.reference_doctype || !t.reference_id) return
  router.push(docUrl(t.reference_doctype, t.reference_id))
}

function openNotification(n: MyWork['notifications'][number]) {
  if (n.doctype && n.doc_id) {
    router.push(docUrl(n.doctype, n.doc_id))
  }
}

function formatDue(due: string | null): string {
  if (!due) return ''
  return formatIntl(due, { day: '2-digit', month: '2-digit' })
}

onMounted(async () => {
  try {
    data.value = await workspaceApi.getMyWork()
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="overflow-hidden rounded-lg border bg-card">
    <Tabs default-value="tasks" class="gap-0">
      <div class="border-b p-2">
        <TabsList class="w-full">
          <TabsTrigger value="tasks" class="gap-1.5">
            <CheckSquare class="size-3.5" />
            Задачі
            <Badge v-if="assignedCount" variant="secondary" class="px-1.5">{{ assignedCount }}</Badge>
          </TabsTrigger>
          <TabsTrigger value="notifications" class="gap-1.5">
            <Bell class="size-3.5" />
            Сповіщення
            <Badge v-if="unreadCount" variant="secondary" class="px-1.5">{{ unreadCount }}</Badge>
          </TabsTrigger>
        </TabsList>
      </div>

      <div v-if="loading" class="flex items-center justify-center gap-3 py-10 text-muted-foreground">
        <Spinner class="size-4" />
        Завантаження...
      </div>

      <template v-else>
        <TabsContent value="tasks" class="mt-0">
          <div v-if="!data?.assigned.length" class="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <CheckSquare class="size-5 text-muted-foreground/40" />
            <p class="text-muted-foreground">Немає призначених задач</p>
          </div>
          <button v-for="t in data!.assigned.slice(0, 8)" :key="t.id"
            class="group flex w-full items-start gap-3 border-b px-4 py-3 text-left transition-colors last:border-0 hover:bg-accent"
            @click="openTask(t)">
            <div class="min-w-0 flex-1">
              <p class="truncate font-medium text-foreground transition-colors group-hover:text-primary">
                {{ t.title }}
              </p>
              <p v-if="taskNote(t)" class="truncate text-muted-foreground">{{ taskNote(t) }}</p>
              <div class="flex items-center gap-1.5 text-muted-foreground/70">
                <span class="font-mono">{{ t.reference_doctype }}</span>
                <template v-if="t.overdue">
                  <span>·</span>
                  <span class="font-medium text-destructive">прострочено</span>
                </template>
                <template v-else-if="t.due_date">
                  <span>·</span>
                  <span class="tabular-nums">{{ formatDue(t.due_date) }}</span>
                </template>
              </div>
            </div>
          </button>
        </TabsContent>

        <TabsContent value="notifications" class="mt-0">
          <div v-if="!data?.notifications.length" class="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <Bell class="size-5 text-muted-foreground/40" />
            <p class="text-muted-foreground">Немає нових сповіщень</p>
          </div>
          <button v-for="n in data!.notifications.slice(0, 8)" :key="n.name"
            class="group flex w-full items-start gap-3 border-b px-4 py-3 text-left transition-colors last:border-0 hover:bg-accent"
            :class="{ 'cursor-default': !n.doctype }"
            @click="openNotification(n)">
            <div class="mt-1.5 size-1.5 shrink-0 rounded-full bg-info" />
            <p class="min-w-0 flex-1 text-foreground transition-colors group-hover:text-primary">
              {{ n.subject }}
            </p>
          </button>
        </TabsContent>
      </template>
    </Tabs>
  </div>
</template>
