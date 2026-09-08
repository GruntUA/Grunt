<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAttachChannels } from '@/core/attachmentChannels/registry'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const props = defineProps<{
  open: boolean
  imageOnly?: boolean
  attachedToDoctype?: string
  attachedToId?: string
  /** Let channels that support it (Library) return several files at once. */
  multiple?: boolean
  /** URL currently stored in the field — passed through for an "attached" marker. */
  currentUrl?: string | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [result: AttachmentResult]
  selectMany: [results: AttachmentResult[]]
}>()

const { t } = useI18n()

const channels = computed(() => getAttachChannels(props.imageOnly ?? false))
const activeId = ref<string>('')

// Reset active channel when dialog opens or channels change
const activeChannel = computed(() => {
  const list = channels.value
  if (!list.find(c => c.id === activeId.value)) {
    activeId.value = list[0]?.id ?? ''
  }
  return list.find(c => c.id === activeId.value) ?? list[0]
})

function onSelect(result: AttachmentResult) {
  emit('select', result)
  emit('update:open', false)
}

function onSelectMany(results: AttachmentResult[]) {
  emit('selectMany', results)
  emit('update:open', false)
}

function onNavKeydown(e: KeyboardEvent) {
  const list = channels.value
  const i = list.findIndex(c => c.id === activeId.value)
  if (i < 0) return
  const next = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: list.length - 1 }[e.key]
  if (next === undefined) return
  e.preventDefault()
  const target = list[Math.max(0, Math.min(list.length - 1, next))]
  if (target) activeId.value = target.id
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-2xl p-0 overflow-hidden flex flex-col max-h-[85vh]">
    <DialogHeader class="px-4 pt-4 shrink-0">
      <DialogTitle class="font-semibold">
        {{ imageOnly ? t('Attach an image') : t('Attach a file') }}
      </DialogTitle>
    </DialogHeader>
    <div class="flex min-h-[400px] flex-1 overflow-hidden">
        <!-- Sidebar -->
        <nav
          class="w-40 shrink-0 border-r border-border flex flex-col gap-0.5 p-2 overflow-y-auto"
          role="tablist"
          aria-orientation="vertical"
          @keydown="onNavKeydown"
        >
          <button
            v-for="ch in channels"
            :id="`attach-tab-${ch.id}`"
            :key="ch.id"
            type="button"
            role="tab"
            :aria-selected="activeChannel?.id === ch.id"
            :aria-controls="`attach-panel-${ch.id}`"
            :tabindex="activeChannel?.id === ch.id ? 0 : -1"
            class="flex items-center gap-2.5 px-3 py-2 rounded-md transition-colors text-left w-full"
            :class="activeChannel?.id === ch.id
              ? 'bg-primary/10 text-primary font-medium border-l-2 border-primary pl-[10px]'
              : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
            @click="activeId = ch.id"
          >
            <component :is="ch.icon" class="size-4 shrink-0" />
            <span class="truncate">{{ ch.label }}</span>
          </button>
        </nav>

        <!-- Channel content -->
        <div
          v-if="activeChannel"
          :id="`attach-panel-${activeChannel.id}`"
          class="flex-1 overflow-y-auto"
          role="tabpanel"
          :aria-labelledby="`attach-tab-${activeChannel.id}`"
        >
          <component
            :is="activeChannel.component"
            :image-only="imageOnly ?? false"
            :attached-to-doctype="attachedToDoctype"
            :attached-to-id="attachedToId"
            :multiple="multiple ?? false"
            :current-url="currentUrl ?? null"
            @select="onSelect"
            @select-many="onSelectMany"
          />
        </div>
        <div v-else class="flex-1 flex items-center justify-center text-muted-foreground">
          {{ t('No attachment sources available') }}
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
