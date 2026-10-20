<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { useServerError } from '@/core/composables/useServerError'
import { X, ChevronDown } from '@lucide/vue'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import {
  CodeBlock,
  CodeBlockActions,
  CodeBlockContent,
  CodeBlockCopyButton,
  CodeBlockFooter,
  CodeBlockHeader,
  CodeBlockLine,
  CodeBlockTitle,
  CodeBlockToken,
  useHighlightedCode,
} from '@/components/ui/code-block'

const { t } = useI18n()

const { state, close } = useServerError()

const showFullTraceback = ref(false)

const tracebackLines = computed(() => {
  const tb = state.value.debug?.traceback ?? ''
  return tb.split('\n').filter(Boolean)
})

// Show last N lines by default, expand to all
const PREVIEW_LINES = 12
const visibleLines = computed(() =>
  showFullTraceback.value ? tracebackLines.value : tracebackLines.value.slice(-PREVIEW_LINES)
)

const sqlLines = useHighlightedCode(() => state.value.debug?.sql ?? '', 'sql')

// Shared look of every block on the modal's fixed dark-red palette
const blockClass = 'border-red-900/20 bg-black/40 text-red-100/90 dark:bg-black/40'
const titleClass = 'font-mono text-xs font-normal uppercase tracking-wider text-red-400/60'

const reportText = computed(() => {
  const d = state.value.debug
  if (!d) return ''
  return [
    `${state.value.status} ${d.exc_type}: ${d.message}`,
    d.fields?.length
      ? `\nFields:\n${d.fields.map(f => `  ${f.loc}: ${f.msg} (got ${f.input})`).join('\n')}`
      : '',
    d.sql ? `\nSQL:\n${d.sql}` : '',
    d.sql_params ? `\nParams: ${d.sql_params}` : '',
    d.db_error ? `\nDB Error: ${d.db_error}` : '',
    `\nTraceback:\n${tracebackLines.value.join('\n')}`,
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
                <span class="text-red-400">{{ state.debug.exc_type }}</span>:
                {{ state.debug.message }}
              </p>
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
              <CodeBlock size="sm" :class="blockClass">
                <CodeBlockHeader>
                  <CodeBlockTitle :class="titleClass">SQL Query</CodeBlockTitle>
                  <CodeBlockActions>
                    <CodeBlockCopyButton
                      :value="state.debug.sql"
                      class="text-red-400/60 hover:text-red-300 hover:bg-red-900/30"
                      :aria-label="t('Copy')"
                    />
                  </CodeBlockActions>
                </CodeBlockHeader>
                <CodeBlockContent wrap>
                  <CodeBlockLine v-for="(line, i) in sqlLines" :key="i">
                    <CodeBlockToken v-for="(token, j) in line" :key="j" :token="token" />
                  </CodeBlockLine>
                </CodeBlockContent>
              </CodeBlock>
              <CodeBlock v-if="state.debug.sql_params" size="sm" :class="blockClass">
                <CodeBlockHeader>
                  <CodeBlockTitle :class="titleClass">Parameters</CodeBlockTitle>
                </CodeBlockHeader>
                <CodeBlockContent class="text-yellow-200/80">{{ state.debug.sql_params }}</CodeBlockContent>
              </CodeBlock>
              <CodeBlock v-if="state.debug.db_error" size="sm" :class="blockClass">
                <CodeBlockHeader>
                  <CodeBlockTitle :class="titleClass">Database Error</CodeBlockTitle>
                </CodeBlockHeader>
                <CodeBlockContent wrap class="text-orange-300/90">{{ state.debug.db_error }}</CodeBlockContent>
              </CodeBlock>
              <div class="border-t border-red-900/20" />
            </template>

            <!-- Traceback -->
            <CodeBlock v-if="state.debug?.traceback" size="sm" :class="blockClass">
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
