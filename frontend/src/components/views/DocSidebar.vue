<script setup lang="ts">
import { useAttrs } from 'vue'
import { PanelRightClose, User } from '@lucide/vue'
import type { DocType, GruntDocument } from '@/types'
import type { PresenceUser } from '@/core/composables/usePresence'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import DocSidebarBody from './sidebar/DocSidebarBody.vue'
import { useDocPanel } from './sidebar/useDocPanel'

defineProps<{
  doctype: DocType
  document: GruntDocument
  workspace?: string
  users?: PresenceUser[]
}>()

const attrs = useAttrs()
defineOptions({ inheritAttrs: false })

const { open, openMobile, isMobile, state, width, toggle, setWidth, MIN_WIDTH } = useDocPanel()

// ── Desktop resize handle ───────────────────────────────────────────────────
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
    <div
      class="form-section bg-card border border-border/60 rounded-lg shadow-sm overflow-hidden"
      :style="{ width: `${Math.max(width, MIN_WIDTH)}px` }"
    >
      <div class="form-section-header border-b border-border/60 px-4 py-3 flex items-center gap-2">
        <User class="size-3.5 text-muted-foreground" />
        <span class="flex-1 font-semibold uppercase tracking-wider">Деталі</span>
        <Button variant="ghost" size="icon" class="size-6 -mr-1.5" title="Згорнути (Ctrl+])" @click="toggle">
          <PanelRightClose class="size-4" />
        </Button>
      </div>
      <div class="form-section-body p-4">
        <DocSidebarBody :doctype="doctype" :document="document" :workspace="workspace" :users="users" />
      </div>
    </div>
  </aside>

  <!-- Mobile: off-canvas sheet -->
  <Sheet v-else v-model:open="openMobile">
    <SheetContent side="right" class="w-[19rem] sm:max-w-sm p-0 overflow-y-auto">
      <SheetHeader class="border-b border-border/60 px-4 py-3">
        <SheetTitle class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider">
          <User class="size-3.5 text-muted-foreground" />
          Деталі
        </SheetTitle>
      </SheetHeader>
      <div class="p-4">
        <DocSidebarBody :doctype="doctype" :document="document" :workspace="workspace" :users="users" />
      </div>
    </SheetContent>
  </Sheet>
</template>
