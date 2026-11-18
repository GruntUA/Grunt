<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { useServerError } from '@/core/composables/useServerError'
import { docsApi } from '@/core/api/docs'
import { docUrl } from '@/core/workspaceUrl'
import { X, ChevronDown, ExternalLink } from '@lucide/vue'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import {
  CodeBlock,
  CodeBlockContent,
  CodeBlockCopyButton,
  CodeBlockFooter,
  CodeBlockHeader,
  CodeBlockLine,
  CodeBlockTitle,
} from '@/components/ui/code-block'

const { t } = useI18n()

const { state, close } = useServerError()

// The response names only the exception type and its ErrorLog record; the
// message (with SQL / failing fields) and the traceback are read from there.
interface ErrorLogRecord { error_message?: string; traceback?: string }
const record = ref<ErrorLogRecord | null>(null)
const loadFailed = ref(false)

watch(
  () => state.value.open && state.value.debug?.error_log,
  async (name) => {
    record.value = null
    loadFailed.value = false
    showFullTraceback.value = false
    if (!name) return
    try {
      record.value = await docsApi.get('ErrorLog', name) as ErrorLogRecord
    } catch {
      loadFailed.value = true
    }
  },
  { immediate: true },
)

const errorLogUrl = computed(() => {
  const name = state.value.debug?.error_log
  return name ? docUrl('ErrorLog', name) : ''
})

const showFullTraceback = ref(false)

const tracebackLines = computed(() => (record.value?.traceback ?? '').split('\n').filter(Boolean))

// Show last N lines by default, expand to all
const PREVIEW_LINES = 12
const visibleLines = computed(() =>
  showFullTraceback.value ? tracebackLines.value : tracebackLines.value.slice(-PREVIEW_LINES)
)

// Shared look of every block on the modal's fixed dark-red palette
const blockClass = 'border-red-900/20 bg-black/40 text-red-100/90 dark:bg-black/40'
const titleClass = 'font-mono text-xs font-normal uppercase tracking-wider text-red-400/60'

const reportText = computed(() => {
  const d = state.value.debug
  if (!d) return ''
  return [
    `${state.value.status} ${d.exc_type}`,
    d.error_log ? ` (ErrorLog ${d.error_log})` : '',
    d.request_id ? `\nRequest ID: ${d.request_id}` : '',
    record.value?.error_message ? `\n\n${record.value.error_message}` : '',
    tracebackLines.value.length ? `\n\nTraceback:\n${tracebackLines.value.join('\n')}` : '',
  ].join('')
})

function tracebackLineClass(line: string, idx: number) {
  const trimmed = line.trim()
  if (idx === visibleLines.value.length - 1 && !showFullTraceback.value)
    return 'bg-red-900/20 font-semibold text-red-200/90'
  if (line.startsWith('  File')) return 'text-red-300/50'
  if (trimmed.startsWith('raise') || trimmed.startsWith('return')) return 'text-yellow-200/70'
  return 'text-red-100/80'
}
</script>

<template>
  <Dialog :open="state.open" @update:open="(v: boolean) => { if (!v) close() }">
    <!-- `dark` keeps highlight tokens and ui primitives on dark colors in both app themes -->
    <DialogContent
      :show-close-button="false"
      class="dark w-full max-w-3xl max-h-[90vh] flex flex-col rounded-lg overflow-hidden shadow-md border border-red-900/40 bg-[#1a0a0a] p-0 gap-0"
    >
          <!-- Header -->
          <div class="flex items-start gap-3 px-5 py-4 border-b border-red-900/30 bg-[#1f0c0c]">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="inline-flex items-center px-2 py-0.5 rounded font-mono font-semibold bg-red-900/60 text-red-300 border border-red-800/50">
                  {{ state.status }}
                </span>
                <span class="text-red-400/70 font-mono">{{ state.status >= 500 ? 'Internal Server Error' : 'Server-side Error' }}</span>
              </div>
              <p class="font-mono text-red-200 font-semibold break-words" v-if="state.debug">
                <span class="text-red-400">{{ state.debug.exc_type }}</span>
                <a
                  v-if="errorLogUrl"
                  :href="errorLogUrl"
                  target="_blank"
                  class="ml-2 inline-flex items-center gap-1 font-normal text-red-300/70 hover:text-red-200 underline"
                >ErrorLog {{ state.debug.error_log }} <ExternalLink class="size-3" /></a>
              </p>
              <p v-if="state.debug?.request_id" class="font-mono text-red-400/50">Request ID: {{ state.debug.request_id }}</p>
              <p class="text-red-300/80" v-else>{{ state.plainMessage }}</p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <CodeBlockCopyButton
                v-if="state.debug"
                :value="reportText"
                size="icon-sm"
                class="text-red-400/60 hover:text-red-300 hover:bg-red-900/30 [&_svg:not([class*='size-'])]:size-4"
                :aria-label="t('Copy')"
                :title="t('Copy')"
              />
              <button
                @click="close"
                class="p-1.5 rounded text-red-400/60 hover:text-red-300 hover:bg-red-900/30 transition-colors"
              >
                <X class="size-4" />
              </button>
            </div>
          </div>

          <!-- Body -->
          <div class="flex-1 overflow-y-auto p-5 space-y-4 font-mono">
            <p v-if="state.debug?.error_log && !record && !loadFailed" class="text-red-400/50">{{ t('Loading…') }}</p>
            <p v-if="loadFailed" class="text-red-300/80">{{ t('Open the Error Log record for the traceback.') }}</p>

            <!-- Message: the exception text, with SQL / failing fields -->
            <CodeBlock v-if="record?.error_message" size="sm" :class="blockClass">
              <CodeBlockHeader>
                <CodeBlockTitle :class="titleClass">Message</CodeBlockTitle>
              </CodeBlockHeader>
              <CodeBlockContent wrap class="text-orange-300/90">{{ record.error_message }}</CodeBlockContent>
            </CodeBlock>

            <!-- Traceback -->
            <CodeBlock v-if="tracebackLines.length" size="sm" :class="blockClass">
              <CodeBlockHeader>
                <CodeBlockTitle :class="titleClass">Traceback</CodeBlockTitle>
              </CodeBlockHeader>
              <CodeBlockContent>
                <CodeBlockLine
                  v-for="(line, idx) in visibleLines"
                  :key="idx"
                  :variant="idx === visibleLines.length - 1 && !showFullTraceback ? 'highlighted' : 'default'"
                  :class="tracebackLineClass(line, idx)"
                >{{ line }}</CodeBlockLine>
              </CodeBlockContent>

              <!-- Show more -->
              <CodeBlockFooter
                v-if="!showFullTraceback && tracebackLines.length > PREVIEW_LINES"
                class="border-t border-red-900/20 p-0 group-data-[size=sm]/code-block:p-0"
              >
                <button
                  @click="showFullTraceback = true"
                  class="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-red-400/60 hover:text-red-300 hover:bg-red-900/20 transition-colors"
                >
                  <ChevronDown class="size-3" />
                  {{ t('Show all {n} lines', { n: String(tracebackLines.length) }) }}
                </button>
              </CodeBlockFooter>
            </CodeBlock>
          </div>

          <!-- Footer hint -->
          <div class="px-5 py-2.5 border-t border-red-900/30 bg-[#1f0c0c] text-red-400/40 font-mono">
            {{ t('Shown only in debug mode · Click outside or press ESC to close') }}
          </div>
    </DialogContent>
  </Dialog>
</template>
