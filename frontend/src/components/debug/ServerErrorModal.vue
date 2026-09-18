<script setup lang="ts">
import { computed } from 'vue'
import { useServerError } from '@/core/composables/useServerError'
import { X, Copy, ChevronDown } from '@lucide/vue'
import { ref } from 'vue'
import { Dialog, DialogContent } from '@/components/ui/dialog'

const { state, close } = useServerError()

const showFullTraceback = ref(false)
const copied = ref(false)

const tracebackLines = computed(() => {
  const tb = state.value.debug?.traceback ?? ''
  return tb.split('\n').filter(Boolean)
})

// Show last N lines by default, expand to all
const PREVIEW_LINES = 12
const visibleLines = computed(() =>
  showFullTraceback.value ? tracebackLines.value : tracebackLines.value.slice(-PREVIEW_LINES)
)

function copyAll() {
  const d = state.value.debug
  if (!d) return
  const text = [
    `${state.value.status} ${d.exc_type}: ${d.message}`,
    d.fields?.length
      ? `\nFields:\n${d.fields.map(f => `  ${f.loc}: ${f.msg} (got ${f.input})`).join('\n')}`
      : '',
    d.sql ? `\nSQL:\n${d.sql}` : '',
    d.sql_params ? `\nParams: ${d.sql_params}` : '',
    d.db_error ? `\nDB Error: ${d.db_error}` : '',
    `\nTraceback:\n${visibleLines.value.join('\n')}`,
  ].join('')
  navigator.clipboard.writeText(text).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}
</script>

<template>
  <Dialog :open="state.open" @update:open="(v: boolean) => { if (!v) close() }">
    <DialogContent
      :show-close-button="false"
      class="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-lg overflow-hidden shadow-md border border-red-900/40 bg-[#1a0a0a] p-0 gap-0"
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
                <span class="text-red-400">{{ state.debug.exc_type }}</span>:
                {{ state.debug.message }}
              </p>
              <p class="text-red-300/80" v-else>{{ state.plainMessage }}</p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button
                @click="copyAll"
                class="p-1.5 rounded text-red-400/60 hover:text-red-300 hover:bg-red-900/30 transition-colors"
                :title="copied ? 'Скопійовано!' : 'Копіювати'"
              >
                <Copy class="size-4" />
              </button>
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
            <!-- Validation fields block -->
            <template v-if="state.debug?.fields?.length">
              <div>
                <div class="text-red-400/60 uppercase tracking-wider mb-2">Fields</div>
                <div class="bg-black/40 border border-red-900/20 rounded-lg divide-y divide-red-900/20">
                  <div v-for="(f, idx) in state.debug.fields" :key="idx" class="px-4 py-2">
                    <div class="text-yellow-200/90">{{ f.loc }} <span class="text-red-400/50">({{ f.type }})</span></div>
                    <div class="text-red-100/80">{{ f.msg }}</div>
                    <div class="text-red-400/50 truncate">input: {{ f.input }}</div>
                  </div>
                </div>
              </div>
              <div class="border-t border-red-900/20" />
            </template>

            <!-- SQL block -->
            <template v-if="state.debug?.sql">
              <div>
                <div class="text-red-400/60 uppercase tracking-wider mb-2">SQL Query</div>
                <pre class="bg-black/40 border border-red-900/20 rounded-lg p-4 text-red-100/90 overflow-x-auto leading-relaxed whitespace-pre-wrap break-all">{{ state.debug.sql }}</pre>
              </div>
              <div v-if="state.debug.sql_params">
                <div class="text-red-400/60 uppercase tracking-wider mb-2">Parameters</div>
                <pre class="bg-black/40 border border-red-900/20 rounded-lg p-3 text-yellow-200/80 overflow-x-auto">{{ state.debug.sql_params }}</pre>
              </div>
              <div v-if="state.debug.db_error">
                <div class="text-red-400/60 uppercase tracking-wider mb-2">Database Error</div>
                <pre class="bg-black/40 border border-red-900/20 rounded-lg p-3 text-orange-300/90 overflow-x-auto">{{ state.debug.db_error }}</pre>
              </div>
              <div class="border-t border-red-900/20" />
            </template>

            <!-- Traceback -->
            <div v-if="state.debug?.traceback">
              <div class="text-red-400/60 uppercase tracking-wider mb-2">Traceback</div>
              <div class="bg-black/40 border border-red-900/20 rounded-lg overflow-hidden">
                <div class="overflow-x-auto">
                  <div
                    v-for="(line, idx) in visibleLines"
                    :key="idx"
                    class="px-4 py-0.5 leading-5 whitespace-pre"
                    :class="{
                      'text-red-300/50': line.startsWith('  File'),
                      'text-yellow-200/70': line.trim().startsWith('raise') || line.trim().startsWith('return'),
                      'text-red-200/90 font-semibold bg-red-900/20': idx === visibleLines.length - 1 && !showFullTraceback,
                      'text-red-100/80': !line.startsWith('  File') && !line.trim().startsWith('raise'),
                    }"
                  >{{ line }}</div>
                </div>

                <!-- Show more -->
                <button
                  v-if="!showFullTraceback && tracebackLines.length > PREVIEW_LINES"
                  @click="showFullTraceback = true"
                  class="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-red-400/60 hover:text-red-300 hover:bg-red-900/20 transition-colors border-t border-red-900/20"
                >
                  <ChevronDown class="size-3" />
                  Показати всі {{ tracebackLines.length }} рядків
                </button>
              </div>
            </div>
          </div>

          <!-- Footer hint -->
          <div class="px-5 py-2.5 border-t border-red-900/30 bg-[#1f0c0c] text-red-400/40 font-mono">
            Показується лише в режимі debug · Натисни поза вікном або ESC щоб закрити
          </div>
    </DialogContent>
  </Dialog>
</template>
