<script setup lang="ts">
import { ref } from 'vue'
import draggable from 'vuedraggable'
import type { LayoutTab } from '@/core/composables/useFormLayout'

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
  <div class="flex items-center gap-0 border-b border-[--grunt-border] bg-[--grunt-surface] px-2 shrink-0">
    <draggable
      :model-value="tabs"
      item-key="_fieldname"
      class="flex items-center gap-0"
      ghost-class="opacity-30"
      direction="horizontal"
      :animation="200"
      @update:model-value="emit('update:tabs', $event)"
    >
      <template #item="{ element: tab, index: i }">
        <div
          class="relative flex items-center gap-1 px-3 py-2.5 cursor-pointer select-none group"
          :class="activeIndex === i
            ? 'text-[--grunt-primary]'
            : 'text-[--grunt-text-secondary] hover:text-[--grunt-text-primary]'"
          @click="emit('update:activeIndex', i)"
          @dblclick.stop="startRename(tab)"
        >
          <!-- Editing mode -->
          <template v-if="editingTab === tab._fieldname">
            <input
              v-model="editLabel"
              type="text"
              class="text-sm font-medium bg-transparent border-b border-[--grunt-primary] outline-none w-24 px-0 py-0"
              @blur="finishRename(tab)"
              @keydown.enter="finishRename(tab)"
              @keydown.escape="cancelRename"
              @click.stop
              autofocus
            />
          </template>
          <template v-else>
            <span class="text-sm font-medium whitespace-nowrap">
              {{ tab.label || 'Main' }}
            </span>
          </template>

          <!-- Delete tab (only for explicit tabs, not the default one) -->
          <button
            v-if="tab._field && tabs.length > 1"
            type="button"
            class="text-[--grunt-text-muted] hover:text-[--grunt-danger] text-xs opacity-0 group-hover:opacity-100 transition-opacity ml-1"
            @click.stop="emit('deleteTab', tab._fieldname)"
          >×</button>

          <!-- Active indicator -->
          <div
            v-if="activeIndex === i"
            class="absolute bottom-0 left-2 right-2 h-0.5 bg-[--grunt-primary] rounded-t"
          />
        </div>
      </template>
    </draggable>

    <!-- Add tab button -->
    <button
      type="button"
      class="px-3 py-2.5 text-sm text-[--grunt-text-muted] hover:text-[--grunt-primary] transition-colors shrink-0"
      title="Add tab"
      @click="emit('addTab')"
    >+</button>
  </div>
</template>
