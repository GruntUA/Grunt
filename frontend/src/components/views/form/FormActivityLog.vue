<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { History, ChevronDown } from 'lucide-vue-next'
import { Spinner } from '@/components/ui/spinner'

interface ActivityEntry {
  id: string
  action: string
  user: string
  details: Record<string, unknown> | null
  created_at: string | null
}

const props = defineProps<{
  doctype: string
  id: string | null
}>()

const { t } = useI18n()
const showLog = ref(false)
const activityLog = ref<ActivityEntry[]>([])
const logLoading = ref(false)

async function loadLog() {
  if (!props.id) return
  logLoading.value = true
  try {
    const { default: client } = await import('@/core/api/client')
    const r = await client.get(`/api/v1/docs/${props.doctype}/${props.id}/log`)
    activityLog.value = (r.data?.data ?? []) as ActivityEntry[]
  } catch {
    // ignore
  } finally {
    logLoading.value = false
  }
}

function toggleLog() {
  showLog.value = !showLog.value
  if (showLog.value && activityLog.value.length === 0) loadLog()
}

// Expose toggleLog so the header can trigger it
defineExpose({ toggleLog, forceReload: loadLog })
</script>

<template>
  <div v-if="id" class="mt-4 bg-card rounded-xl overflow-hidden shadow-sm ring-1 ring-border/60 transition-all duration-300">
    <button type="button"
      class="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:bg-muted/50"
      @click="toggleLog">
      <History class="size-4" />
      <span class="flex-1 text-left">{{ t('Activity log') }}</span>
      <ChevronDown class="size-4 transition-transform duration-300" :class="{ 'rotate-180': showLog }" />
    </button>
    <Transition name="log">
      <div v-if="showLog" class="border-t border-border px-5 py-4 bg-muted/20">
        <div v-if="logLoading" class="flex justify-center py-6">
          <Spinner size="sm" />
        </div>
        <div v-else-if="activityLog.length === 0" class="text-sm text-muted-foreground py-4 text-center italic">
          Записів немає
        </div>
        <ul v-else class="space-y-4">
          <li v-for="entry in activityLog" :key="entry.id" class="flex items-start gap-3 text-sm animate-in fade-in slide-in-from-top-1">
            <div class="flex flex-col gap-1 flex-1">
              <div class="flex items-center gap-2">
                <span class="font-bold text-foreground">{{ entry.user }}</span>
                <span class="text-muted-foreground">{{ entry.action }}</span>
              </div>
              <div class="text-[11px] text-muted-foreground/80 flex items-center gap-1">
                <span v-if="entry.created_at">{{ new Date(entry.created_at).toLocaleString('uk-UA') }}</span>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.log-enter-active,
.log-leave-active {
  transition: opacity 300ms cubic-bezier(0.4, 0, 0.2, 1), max-height 300ms cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.log-enter-from,
.log-leave-to {
  opacity: 0;
  max-height: 0;
}

.log-enter-to,
.log-leave-from {
  opacity: 1;
  max-height: 1000px;
}
</style>
