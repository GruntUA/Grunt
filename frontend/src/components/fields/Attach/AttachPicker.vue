<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAttachChannels } from '@/core/attachmentChannels/registry'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const props = defineProps<{
  open: boolean
  imageOnly?: boolean
  attachedToDoctype?: string
  attachedToId?: string
  /** Let channels that support it (Library) return several files at once. */
  multiple?: boolean
  /** URL currently stored in the field - passed through for an "attached" marker. */
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
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-2xl p-0 overflow-hidden flex flex-col max-h-[85vh]">
    <DialogHeader class="px-4 pt-4 pb-3 shrink-0">
      <DialogTitle class="font-semibold">
        {{ imageOnly ? t('Attach an image') : t('Attach a file') }}
      </DialogTitle>
    </DialogHeader>
    <Tabs
      v-if="activeChannel"
      :model-value="activeChannel.id"
      orientation="vertical"
      class="min-h-[400px] flex-1 flex-row gap-0 overflow-hidden border-t"
      @update:model-value="activeId = String($event)"
    >
      <TabsList class="h-auto w-40 shrink-0 flex-col items-stretch justify-start gap-0.5 rounded-none border-r bg-transparent p-2">
        <TabsTrigger
          v-for="ch in channels"
          :key="ch.id"
          :value="ch.id"
          class="h-9 flex-none justify-start gap-2.5 px-3 text-muted-foreground data-[state=active]:bg-muted data-[state=active]:text-foreground data-[state=active]:shadow-none"
        >
          <component :is="ch.icon" />
          <span class="truncate">{{ t(ch.label) }}</span>
        </TabsTrigger>
      </TabsList>
      <TabsContent v-for="ch in channels" :key="ch.id" :value="ch.id" class="overflow-y-auto">
        <component
          :is="ch.component"
          :image-only="imageOnly ?? false"
          :attached-to-doctype="attachedToDoctype"
          :attached-to-id="attachedToId"
          :multiple="multiple ?? false"
          :current-url="currentUrl ?? null"
          @select="onSelect"
          @select-many="onSelectMany"
        />
      </TabsContent>
    </Tabs>
    <div v-else class="flex min-h-[400px] flex-1 items-center justify-center border-t text-muted-foreground">
      {{ t('No attachment sources available') }}
    </div>
    </DialogContent>
  </Dialog>
</template>
