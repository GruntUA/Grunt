<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { Plus, X } from '@lucide/vue'
import { VueDraggable } from 'vue-draggable-plus'
import type { LayoutTab } from '@/core/composables/useFormLayout'
import { useBuilderStore } from '@/stores/builder'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const { t } = useI18n()
const builder = useBuilderStore()

defineProps<{
  tabs: LayoutTab[]
  activeIndex: number
}>()

const emit = defineEmits<{
  'update:activeIndex': [index: number]
  'update:tabs': [tabs: LayoutTab[]]
  addTab: []
  renameTab: [fieldname: string, label: string]
  deleteTab: [fieldname: string]
}>()

const editingTab = ref<string | null>(null)
const editLabel = ref('')
let hoverTimer: ReturnType<typeof setTimeout> | null = null

function onTabDragOver(event: DragEvent, index: number) {
  event.preventDefault()
  if (hoverTimer !== null) return
  hoverTimer = setTimeout(() => {
    emit('update:activeIndex', index)
    hoverTimer = null
  }, 600)
}

function onTabDragLeave() {
  if (hoverTimer !== null) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
}

function startRename(tab: LayoutTab) {
  if (!tab._field) return
  editLabel.value = tab.label
  editingTab.value = tab._fieldname
}

function finishRename(tab: LayoutTab) {
  if (editingTab.value === tab._fieldname) {
    emit('renameTab', tab._fieldname, editLabel.value)
    editingTab.value = null
  }
}

function cancelRename() {
  editingTab.value = null
}
</script>

<template>
  <div class="flex items-center gap-0 border-b border-border bg-card px-2 shrink-0">
    <VueDraggable
      :model-value="tabs"
      class="flex items-center gap-0"
      ghost-class="opacity-30"
      direction="horizontal"
      :animation="200"
      @update:model-value="emit('update:tabs', $event)"
    >
      <div
        v-for="(tab, i) in tabs"
        :key="tab._fieldname"
        class="relative flex items-center gap-1 px-3 py-2.5 cursor-pointer select-none group"
        :class="activeIndex === i
          ? 'text-primary'
          : 'text-muted-foreground hover:text-foreground'"
        @click="emit('update:activeIndex', i); if (tab._field) builder.selectField(tab._fieldname)"
        @dblclick.stop="startRename(tab)"
        @dragover="onTabDragOver($event, i)"
        @dragleave="onTabDragLeave"
      >
        <!-- Editing mode -->
        <template v-if="editingTab === tab._fieldname">
          <Input
            v-model="editLabel"
            class="h-7 w-28"
            @blur="finishRename(tab)"
            @keydown.enter="finishRename(tab)"
            @keydown.escape="cancelRename"
            @click.stop
            autofocus
          />
        </template>
        <template v-else>
          <span class="font-medium whitespace-nowrap">
            {{ tab.label || t('Main') }}
          </span>
        </template>

        <!-- Delete tab (only for explicit tabs, not the default one) -->
        <Button
          v-if="tab._field && tabs.length > 1"
          variant="ghost"
          size="icon-xs"
          class="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          :aria-label="t('Delete tab')"
          @click.stop="emit('deleteTab', tab._fieldname)"
        >
          <X />
        </Button>

        <!-- Active indicator -->
        <div
          v-if="activeIndex === i"
          class="absolute bottom-0 left-2 right-2 h-0.5 bg-primary rounded-t"
        />
      </div>
    </VueDraggable>

    <!-- Add tab button -->
    <Button
      variant="ghost"
      size="icon-sm"
      class="mx-1 shrink-0 text-muted-foreground"
      :aria-label="t('Add tab')"
      @click="emit('addTab')"
    >
      <Plus />
    </Button>
  </div>
</template>
