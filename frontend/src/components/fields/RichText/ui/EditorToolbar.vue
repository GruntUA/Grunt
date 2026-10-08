<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Maximize2, Minimize2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { N_ } from '@/plugins/i18n'
import { ALIGNMENTS, BLOCK_STYLES } from '../editor/commands'
import CommandButton from './CommandButton.vue'
import CommandGroupMenu from './CommandGroupMenu.vue'
import FontMenus from './FontMenus.vue'
import LinkPopover from './LinkPopover.vue'
import InsertMenu from './InsertMenu.vue'
import MoreMenu from './MoreMenu.vue'

// The fixed toolbar. It is a size container: on a narrow editor the labels
// collapse to icons and secondary buttons hide (their shortcuts still work).
defineProps<{ documentStyle?: boolean }>()
const fullscreen = defineModel<boolean>('fullscreen', { default: false })

const { t } = useI18n()
</script>

<template>
  <div
    role="toolbar" :aria-label="t('Formatting')"
    class="@container sticky z-10 flex flex-wrap items-center gap-0.5 rounded-t-md border border-b-0 border-border bg-muted p-1 text-muted-foreground"
    :class="fullscreen ? 'top-0 mt-4' : 'top-[var(--richtext-sticky-top,0px)]'"
  >
    <CommandGroupMenu :group="BLOCK_STYLES" :label="N_('Text style')" show-name />
    <FontMenus :document-style />
    <Separator orientation="vertical" class="!mx-0.5 !h-6 !my-0" />
    <CommandButton id="bold" />
    <CommandButton id="italic" />
    <!-- also in the selection bubble, so a narrow toolbar can drop them -->
    <CommandButton id="underline" class="hidden @md:inline-flex" />
    <CommandButton id="strike" class="hidden @md:inline-flex" />
    <Separator orientation="vertical" class="!mx-0.5 !h-6 !my-0" />
    <CommandButton id="bulletList" />
    <CommandButton id="orderedList" />
    <CommandGroupMenu :group="ALIGNMENTS" :label="N_('Alignment')" />
    <Separator orientation="vertical" class="!mx-0.5 !h-6 !my-0" />
    <LinkPopover />
    <InsertMenu />
    <MoreMenu />

    <div class="flex-1" />

    <CommandButton id="undo" class="hidden @2xl:inline-flex" />
    <CommandButton id="redo" class="hidden @2xl:inline-flex" />
    <Button
      size="icon-sm" variant="ghost"
      :title="fullscreen ? `${t('Exit full screen')} · Esc` : t('Full screen')"
      :aria-label="fullscreen ? t('Exit full screen') : t('Full screen')" :aria-pressed="fullscreen"
      @click="fullscreen = !fullscreen"
    >
      <Minimize2 v-if="fullscreen" />
      <Maximize2 v-else />
    </Button>
  </div>
</template>
