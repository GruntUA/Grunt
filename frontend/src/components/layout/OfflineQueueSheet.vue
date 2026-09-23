<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ExternalLink, RefreshCw, Trash2 } from '@lucide/vue'
import { isDisconnected } from '@/core/composables/useNetworkStatus'
import { discard, flush, queue, retry, type QueuedChange } from '@/core/composables/useOfflineQueue'
import { formatDateTime } from '@/core/datetime'
import { docUrl } from '@/core/workspaceUrl'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

/** Changes made offline that are waiting to be sent — and what to do with the stuck ones. */
const open = defineModel<boolean>('open', { default: false })

const router = useRouter()
const busy = ref(false)

const ACTION: Record<QueuedChange['method'], string> = {
  post: 'Створення',
  put: 'Зміна',
  patch: 'Зміна',
  delete: 'Видалення',
}
const STATUS: Record<QueuedChange['status'], { label: string; variant: 'secondary' | 'destructive' | 'outline' }> = {
  pending: { label: 'Очікує надсилання', variant: 'secondary' },
  conflict: { label: 'Конфлікт', variant: 'destructive' },
  failed: { label: 'Відхилено', variant: 'destructive' },
}

const hasPending = computed(() => queue.value.some((c) => c.status === 'pending'))

async function run(fn: () => Promise<unknown>) {
  busy.value = true
  try {
    await fn()
  } finally {
    busy.value = false
  }
}

function openDoc(change: QueuedChange) {
  if (!change.docId) return
  open.value = false
  router.push(docUrl(change.doctype, change.docId))
}
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent class="w-full sm:max-w-md">
      <SheetHeader>
        <SheetTitle>Несинхронізовані зміни</SheetTitle>
        <SheetDescription>
          Зміни документів, зроблені без зв'язку. Вони надсилаються автоматично, щойно з'являється
          мережа; конфлікти та відхилені зміни чекають на ваше рішення.
        </SheetDescription>
      </SheetHeader>

      <div class="flex flex-1 flex-col gap-3 overflow-y-auto px-4">
        <Empty v-if="!queue.length" class="border">
          <EmptyHeader>
            <EmptyTitle>Усе синхронізовано</EmptyTitle>
            <EmptyDescription>Немає змін, що чекають на надсилання.</EmptyDescription>
          </EmptyHeader>
        </Empty>

        <div v-for="change in queue" :key="change.id" class="flex flex-col gap-2 rounded-md border p-3">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-medium">{{ ACTION[change.method] }} · {{ change.doctype }}</div>
              <div class="truncate text-muted-foreground">{{ change.docId || 'новий документ' }}</div>
            </div>
            <Badge :variant="STATUS[change.status].variant" class="shrink-0">{{ STATUS[change.status].label }}</Badge>
          </div>
          <p v-if="change.error" class="text-destructive">{{ change.error }}</p>
          <span class="text-muted-foreground">{{ formatDateTime(new Date(change.timestamp).toISOString()) }}</span>
          <div class="flex flex-wrap justify-end gap-1">
              <Button v-if="change.docId" variant="ghost" size="sm" @click="openDoc(change)">
                <ExternalLink /> Відкрити
              </Button>
              <Button
                v-if="change.status !== 'pending'"
                variant="outline"
                size="sm"
                :disabled="busy || isDisconnected"
                @click="run(() => retry(change.id!))"
              >
                <RefreshCw /> {{ change.status === 'conflict' ? 'Застосувати мої' : 'Повторити' }}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                class="text-destructive"
                :disabled="busy"
                @click="run(() => discard(change.id!))"
              >
                <Trash2 /> Відкинути
              </Button>
          </div>
        </div>
      </div>

      <div v-if="hasPending" class="border-t p-4">
        <Button class="w-full" :disabled="busy || isDisconnected" @click="run(flush)">
          <RefreshCw /> {{ isDisconnected ? "Чекаємо на зв'язок…" : 'Надіслати зараз' }}
        </Button>
      </div>
    </SheetContent>
  </Sheet>
</template>
