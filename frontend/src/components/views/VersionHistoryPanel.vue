<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Clock, RotateCcw, ChevronRight, Loader2, User } from '@lucide/vue'
import api from '@/core/api/client'

const props = defineProps<{
  doctype: string
  docId: string
}>()

const emit = defineEmits<{
  restored: []
}>()

interface VersionEntry {
  id: string
  version: number
  user: string
  created_at: string | null
  changes: Record<string, { old: unknown; new: unknown }> | null
}

const { t } = useI18n()
const versions = ref<VersionEntry[]>([])
const loading = ref(false)
const restoring = ref<string | null>(null)
const expanded = ref<string | null>(null)

async function load() {
  loading.value = true
  try {
    const r = await api.get('/api/v1/method/grunt.document.base.Document.get_versions', {
      params: { doctype: props.doctype, doc_id: props.docId },
    })
    versions.value = r.data?.data ?? []
  } catch {
    versions.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.docId, (id) => { if (id) load() }, { immediate: true })

async function restore(versionId: string) {
  if (!confirm(t('Restore document to this version?'))) return
  restoring.value = versionId
  try {
    await api.post('/api/v1/method/grunt.document.base.Document.restore_version', {
      doctype: props.doctype, doc_id: props.docId, version_id: versionId,
    })
    emit('restored')
    await load()
  } catch {
    // ignore
  } finally {
    restoring.value = null
  }
}

function toggleExpand(id: string) {
  expanded.value = expanded.value === id ? null : id
}

function formatTime(val: string | null): string {
  if (!val) return '—'
  return new Date(val).toLocaleString('uk-UA', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function changedFields(changes: VersionEntry['changes']): string[] {
  return Object.keys(changes ?? {})
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'boolean') return val ? t('Yes') : t('No')
  return String(val)
}
</script>

<template>
  <div class="divide-y divide-border/50">
    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-6">
      <Loader2 class="size-5 text-primary animate-spin" />
    </div>

    <!-- Empty -->
    <div v-else-if="versions.length === 0" class="py-5 text-center text-sm text-muted-foreground">
      {{ t('No saved versions') }}
    </div>

    <!-- List -->
    <div v-else>
      <div v-for="v in versions" :key="v.id" class="group">
        <!-- Version row -->
        <div class="flex items-center gap-3 px-5 py-2.5 hover:bg-muted/30 transition-colors">
          <!-- Expand toggle -->
          <button
            v-if="v.changes && changedFields(v.changes).length"
            class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
            @click="toggleExpand(v.id)"
          >
            <ChevronRight
              class="size-3.5 transition-transform duration-150"
              :class="{ 'rotate-90': expanded === v.id }"
            />
          </button>
          <div v-else class="size-3.5 shrink-0" />

          <!-- Version badge -->
          <span class="shrink-0 text-xs font-semibold bg-primary/10 text-primary rounded px-1.5 py-0.5">
            v{{ v.version }}
          </span>

          <!-- User + time -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5 text-xs">
              <User class="size-3 text-muted-foreground shrink-0" />
              <span class="font-medium text-foreground truncate">{{ v.user }}</span>
            </div>
            <div class="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
              <Clock class="size-3 shrink-0" />
              {{ formatTime(v.created_at) }}
            </div>
          </div>

          <!-- Changed fields count -->
          <span v-if="v.changes" class="shrink-0 text-xs text-muted-foreground">
            {{ changedFields(v.changes).length }} поле(й)
          </span>

          <!-- Restore button -->
          <button
            class="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-xs text-muted-foreground hover:text-primary px-2 py-1 rounded-md hover:bg-primary/5"
            :disabled="restoring === v.id"
            @click.stop="restore(v.id)"
          >
            <Loader2 v-if="restoring === v.id" class="size-3 animate-spin" />
            <RotateCcw v-else class="size-3" />
            {{ t('Restore') }}
          </button>
        </div>

        <!-- Expanded diff -->
        <Transition name="diff">
          <div v-if="expanded === v.id && v.changes" class="px-8 pb-3">
            <div class="rounded-lg border bg-muted/20 overflow-hidden text-xs">
              <div v-for="field in changedFields(v.changes)" :key="field"
                class="grid grid-cols-[1fr_auto_1fr] items-center gap-2 px-3 py-1.5 border-b last:border-0">
                <div class="min-w-0">
                  <span class="text-xs font-medium text-muted-foreground uppercase block mb-0.5">{{ field }}</span>
                  <span class="line-through text-muted-foreground/60 truncate block">
                    {{ formatValue(v.changes![field].old) }}
                  </span>
                </div>
                <ChevronRight class="size-3 text-muted-foreground shrink-0" />
                <div class="min-w-0">
                  <span class="text-primary font-medium truncate block">
                    {{ formatValue(v.changes![field].new) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diff-enter-active, .diff-leave-active { transition: all 0.15s ease; }
.diff-enter-from, .diff-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
