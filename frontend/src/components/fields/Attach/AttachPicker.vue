<script setup lang="ts">
import { ref, computed } from 'vue'
import { getAttachChannels } from '@/core/attachmentChannels/registry'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const props = defineProps<{
  open: boolean
  imageOnly?: boolean
  attachedToDoctype?: string
  attachedToId?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [result: AttachmentResult]
}>()

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
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl p-0 overflow-hidden">
    <DialogHeader class="px-4 pt-4">
      <DialogTitle class="font-semibold">{{ imageOnly ? 'Прикріпити зображення' : 'Прикріпити файл' }}</DialogTitle>
    </DialogHeader>
    <div class="flex min-h-[400px]">
        <!-- Sidebar -->
        <nav class="w-40 shrink-0 border-r border-border flex flex-col gap-0.5 p-2">
          <button
            v-for="ch in channels"
            :key="ch.id"
            type="button"
            class="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors text-left w-full"
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
        <div class="flex-1 overflow-y-auto">
          <component
            :is="activeChannel?.component"
            v-if="activeChannel"
            :image-only="imageOnly ?? false"
            :attached-to-doctype="attachedToDoctype"
            :attached-to-id="attachedToId"
            @select="onSelect"
          />
          <div v-else class="flex items-center justify-center h-full text-sm text-muted-foreground">
            Немає доступних джерел
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
