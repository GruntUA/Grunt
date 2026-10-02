<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowRight, ChevronDown, GitCompareArrows } from '@lucide/vue'
import type { DocVersionChange } from '@/core/api/docs'
import type { DocField } from '@/types'
import { tn } from '@/plugins/i18n'
import { formatDate, formatDateTime } from '@/core/datetime'
import { htmlToLine, looksLikeHtml } from '@/lib/htmlText'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

// Field-level diff of one document version, formatted per field type.
const props = defineProps<{
  changes: DocVersionChange[]
  fields: DocField[]
}>()
const emit = defineEmits<{ compare: [] }>()

const { t } = useI18n()

const VISIBLE = 3
const expanded = ref(false)

const fieldMap = computed(() => new Map(props.fields.map((f) => [f.fieldname, f])))

const TEXT_TYPES = new Set(['Text', 'LongText', 'RichText', 'HTMLEditor', 'HTML', 'Code', 'JSON', 'TextEditor', 'Markdown'])
const IMAGE_TYPES = new Set(['Image', 'AttachImage', 'Signature'])

type Kind = 'text' | 'image' | 'plain'
interface Row {
  key: string
  label: string
  kind: Kind
  old: string
  new: string
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)
}

function format(change: DocVersionChange, key: 'old' | 'new', field: DocField | undefined): string {
  const label = key === 'old' ? change.old_label : change.new_label
  if (label) return label
  const v = change[key]
  if (isEmpty(v)) return ''
  const type = field?.fieldtype
  if (type === 'Check' || typeof v === 'boolean') return v && v !== '0' ? t('Yes') : t('No')
  if (type === 'Date') return formatDate(v as string)
  if (type === 'Datetime') return formatDateTime(v as string)
  if (Array.isArray(v)) {
    // Child-table / MultiLink snapshots: rows of objects have no single label.
    if (v.some((x) => x !== null && typeof x === 'object')) return t('{n} rows', { n: String(v.length) })
    return v.map(String).join(', ')
  }
  if (typeof v === 'object') return JSON.stringify(v)
  const s = String(v)
  return TEXT_TYPES.has(type ?? '') || looksLikeHtml(s) ? htmlToLine(s) : s
}

const rows = computed<Row[]>(() =>
  props.changes.map((c) => {
    const field = fieldMap.value.get(c.field)
    const type = field?.fieldtype ?? ''
    return {
      key: c.field,
      label: field?.label ?? c.field,
      kind: IMAGE_TYPES.has(type) ? 'image' : TEXT_TYPES.has(type) ? 'text' : 'plain',
      old: IMAGE_TYPES.has(type) ? String(c.old ?? '') : format(c, 'old', field),
      new: IMAGE_TYPES.has(type) ? String(c.new ?? '') : format(c, 'new', field),
    }
  }),
)
const head = computed(() => rows.value.slice(0, VISIBLE))
const rest = computed(() => rows.value.slice(VISIBLE))
</script>

<template>
  <div class="flex flex-col gap-2">
    <dl class="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-x-4 gap-y-2 rounded-md border bg-muted/30 p-3 text-sm">
      <template v-for="row in [...head, ...(expanded ? rest : [])]" :key="row.key">
        <dt class="truncate text-muted-foreground">{{ row.label }}</dt>
        <dd class="min-w-0">
          <!-- Images: thumbnails -->
          <div v-if="row.kind === 'image'" class="flex items-center gap-2">
            <img v-if="row.old" :src="row.old" alt="" class="size-10 rounded-sm border object-cover opacity-60" />
            <span v-else class="text-muted-foreground">—</span>
            <ArrowRight class="size-3.5 shrink-0 text-muted-foreground" />
            <img v-if="row.new" :src="row.new" alt="" class="size-10 rounded-sm border object-cover" />
            <span v-else class="text-muted-foreground">{{ t('removed') }}</span>
          </div>

          <!-- Long text: the new value, clamped; the old one on hover -->
          <div v-else-if="row.kind === 'text'" class="flex flex-col gap-0.5">
            <p v-if="row.new" class="line-clamp-2 break-words">{{ row.new }}</p>
            <p v-else class="text-muted-foreground">{{ t('cleared') }}</p>
            <Tooltip v-if="row.old">
              <TooltipTrigger as-child>
                <span class="w-fit cursor-default text-xs text-muted-foreground underline decoration-dotted underline-offset-2">
                  {{ t('previous value') }}
                </span>
              </TooltipTrigger>
              <TooltipContent class="max-w-96 whitespace-normal">
                <p class="line-clamp-6">{{ row.old }}</p>
              </TooltipContent>
            </Tooltip>
          </div>

          <!-- Short values: old → new -->
          <div v-else class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            <template v-if="row.old">
              <span class="max-w-full truncate text-muted-foreground line-through">{{ row.old }}</span>
              <ArrowRight class="size-3.5 shrink-0 text-muted-foreground" />
            </template>
            <span v-if="row.new" class="max-w-full truncate font-medium">{{ row.new }}</span>
            <span v-else class="text-muted-foreground">{{ t('cleared') }}</span>
          </div>
        </dd>
      </template>
    </dl>

    <div class="flex flex-wrap items-center gap-1">
      <Button
        v-if="rest.length"
        variant="ghost"
        size="xs"
        class="text-muted-foreground"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        <ChevronDown class="transition-transform" :class="expanded && 'rotate-180'" />
        {{ expanded ? t('Show less') : tn('{n} more change', '{n} more changes', rest.length) }}
      </Button>
      <Button variant="ghost" size="xs" class="text-muted-foreground" @click="emit('compare')">
        <GitCompareArrows />
        {{ t('Compare and restore') }}
      </Button>
    </div>
  </div>
</template>
