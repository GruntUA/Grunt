<script setup lang="ts">
import { useI18n } from 'vue-i18n'
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
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from '@/components/ui/empty'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemTitle } from '@/components/ui/item'

const { t } = useI18n()

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
  if (n.ref_doctype && n.doc_id) {
    router.push(docUrl(n.ref_doctype, n.doc_id))
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
            {{ t('Tasks') }}
            <Badge v-if="assignedCount" variant="secondary" class="px-1.5">{{ assignedCount }}</Badge>
          </TabsTrigger>
          <TabsTrigger value="notifications" class="gap-1.5">
            <Bell class="size-3.5" />
            {{ t('Notifications') }}
            <Badge v-if="unreadCount" variant="secondary" class="px-1.5">{{ unreadCount }}</Badge>
          </TabsTrigger>
        </TabsList>
      </div>

      <div v-if="loading" class="flex items-center justify-center gap-3 py-10 text-muted-foreground">
        <Spinner />
        {{ t('Loading...') }}
      </div>

      <template v-else>
        <TabsContent value="tasks" class="mt-0">
          <Empty v-if="!data?.assigned.length">
            <EmptyHeader>
              <EmptyMedia variant="icon"><CheckSquare /></EmptyMedia>
              <EmptyDescription>{{ t('No assigned tasks') }}</EmptyDescription>
            </EmptyHeader>
          </Empty>
          <ItemGroup v-else>
            <Item v-for="t in data!.assigned.slice(0, 8)" :key="t.id" as="button" size="sm"
              class="w-full text-left hover:bg-accent" @click="openTask(t)">
              <ItemContent class="min-w-0">
                <ItemTitle class="w-full truncate">{{ t.title }}</ItemTitle>
                <ItemDescription v-if="taskNote(t)" class="truncate">{{ taskNote(t) }}</ItemDescription>
                <ItemDescription class="flex items-center gap-1.5">
                  <span class="font-mono">{{ t.reference_doctype }}</span>
                  <template v-if="t.overdue">
                    <span>·</span>
                    <span class="font-medium text-destructive">{{ $t('overdue') }}</span>
                  </template>
                  <template v-else-if="t.due_date">
                    <span>·</span>
                    <span class="tabular-nums">{{ formatDue(t.due_date) }}</span>
                  </template>
                </ItemDescription>
              </ItemContent>
            </Item>
          </ItemGroup>
        </TabsContent>

        <TabsContent value="notifications" class="mt-0">
          <Empty v-if="!data?.notifications.length">
            <EmptyHeader>
              <EmptyMedia variant="icon"><Bell /></EmptyMedia>
              <EmptyDescription>{{ t('No new notifications') }}</EmptyDescription>
            </EmptyHeader>
          </Empty>
          <ItemGroup v-else>
            <Item v-for="n in data!.notifications.slice(0, 8)" :key="n.name" as="button" size="sm"
              class="w-full text-left hover:bg-accent" :class="{ 'cursor-default': !n.ref_doctype }"
              @click="openNotification(n)">
              <ItemContent class="min-w-0">
                <ItemTitle class="w-full">{{ n.subject }}</ItemTitle>
              </ItemContent>
            </Item>
          </ItemGroup>
        </TabsContent>
      </template>
    </Tabs>
  </div>
</template>
