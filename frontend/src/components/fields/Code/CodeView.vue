<script setup lang="ts">
// Read-only code display (Shiki highlighting, line numbers, copy). Used by the
// Code and JSON fields when disabled / read_only.
import { useI18n } from 'vue-i18n'
import {
  CodeBlock,
  CodeBlockActions,
  CodeBlockContent,
  CodeBlockCopyButton,
  CodeBlockLine,
  CodeBlockToken,
  useHighlightedCode,
} from '@/components/ui/code-block'

const props = defineProps<{
  code: string
  language: string
}>()

const { t } = useI18n()

const lines = useHighlightedCode(() => props.code, () => props.language)
</script>

<template>
  <CodeBlock>
    <CodeBlockActions v-if="code">
      <CodeBlockCopyButton :value="code" :aria-label="t('Copy')" />
    </CodeBlockActions>
    <CodeBlockContent :line-numbers="!!code" class="max-h-96">
      <CodeBlockLine v-for="(line, i) in lines" :key="i">
        <CodeBlockToken v-for="(token, j) in line" :key="j" :token="token" />
      </CodeBlockLine>
    </CodeBlockContent>
  </CodeBlock>
</template>
