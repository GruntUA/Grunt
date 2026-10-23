<script setup lang="ts">
import { computed } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import { Paperclip } from '@lucide/vue'
import { extractFileId, linkFilename } from '@/core/fileUtils'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

const url = computed(() =>
  typeof props.value === 'string' && props.value ? props.value : null,
)

// The stored value is a download URL; the server resolves the real filename
// into `<field>__label` (see _resolve_attach_labels in grunt/document/relations.py).
const name = computed(() => {
  if (!url.value) return null
  const label = props.row[`${props.field.fieldname}__label`]
  if (typeof label === 'string' && label) return label
  return extractFileId(url.value) ? url.value : linkFilename(url.value)
})
</script>

<template>
  <a
    v-if="url"
    :href="url"
    target="_blank"
    rel="noopener"
    class="inline-flex max-w-full items-center gap-1.5 text-foreground/90 font-medium hover:underline"
    :title="name ?? undefined"
    @click.stop
  >
    <Paperclip class="size-3.5 shrink-0 text-muted-foreground" />
    <span class="truncate">{{ name }}</span>
  </a>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
