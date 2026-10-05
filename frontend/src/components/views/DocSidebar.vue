<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useAttrs } from 'vue'
import { PanelRightClose } from '@lucide/vue'
import type { DocType, GruntDocument } from '@/types'
import type { PresenceUser } from '@/core/composables/usePresence'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import DocSidebarBody from './sidebar/DocSidebarBody.vue'
import { useDocPanel } from './sidebar/useDocPanel'

const { t } = useI18n()

defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
  imageUrl?: string | null
  imageEditable?: boolean
}>()

const emit = defineEmits<{ 'set-image': [url: string | null] }>()

const attrs = useAttrs()
defineOptions({ inheritAttrs: false })

const { open, openMobile, isMobile, state, width, toggle, setWidth, MIN_WIDTH } = useDocPanel()

// Desktop resize handle
function startResize(e: PointerEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = width.value
  const onMove = (ev: PointerEvent) => setWidth(startWidth + (startX - ev.clientX))
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    document.body.style.userSelect = ''
  }
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
</script>

<template>
  <!-- Desktop: collapsible + resizable column -->
  <aside
    v-if="!isMobile"
    v-bind="attrs"
    :data-state="state"
    :style="{ width: open ? `${width}px` : '0px' }"
    class="relative shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out"
  >
    <div
      class="absolute inset-y-0 left-0 z-10 w-1.5 -ml-0.5 cursor-col-resize hover:bg-primary/20 transition-colors"
      :class="{ 'pointer-events-none opacity-0': !open }"
      @pointerdown="startResize"
    />
    <Card
      class="gap-0 rounded-lg py-0"
      :style="{ width: `${Math.max(width, MIN_WIDTH)}px` }"
    >
      <CardHeader class="flex items-center justify-between border-b px-4 py-3 [.border-b]:pb-3">
        <CardTitle class="text-sm">{{ t('Details') }}</CardTitle>
        <CardAction class="-my-1">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="ghost" size="icon-sm" class="size-7 -mr-1.5" :aria-label="t('Collapse')" @click="toggle">
                <PanelRightClose />
              </Button>
            </TooltipTrigger>
            <TooltipContent class="flex items-center gap-2">
              {{ t('Collapse') }}
              <Kbd>Ctrl ]</Kbd>
            </TooltipContent>
          </Tooltip>
        </CardAction>
      </CardHeader>
      <CardContent class="p-4">
        <DocSidebarBody
          :doctype="doctype" :document="document" :workspace="workspace" :users="users"
          :image-url="imageUrl" :image-editable="imageEditable" @set-image="emit('set-image', $event)"
        />
      </CardContent>
    </Card>
  </aside>

  <!-- Mobile: off-canvas sheet -->
  <Sheet v-else v-model:open="openMobile">
    <SheetContent side="right" class="w-[19rem] sm:max-w-sm p-0 overflow-y-auto">
      <SheetHeader class="border-b border-border/60 px-4 py-3">
        <SheetTitle class="text-sm">{{ t('Details') }}</SheetTitle>
      </SheetHeader>
      <div class="p-4">
        <DocSidebarBody
          :doctype="doctype" :document="document" :workspace="workspace" :users="users"
          :image-url="imageUrl" :image-editable="imageEditable" @set-image="emit('set-image', $event)"
        />
      </div>
    </SheetContent>
  </Sheet>
</template>
