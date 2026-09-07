<script setup lang="ts">
import { ref, watch, provide } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { useBuilderStore } from '@/stores/builder'
import type { LayoutTab, LayoutSection } from '@/core/composables/useFormLayout'
import CanvasTabBar from './CanvasTabBar.vue'
import CanvasSection from './CanvasSection.vue'

const builder = useBuilderStore()
const activeTabIndex = ref(0)

const isDraggingField = ref(false)
provide('fieldDragging', isDraggingField)

// Reset active tab when doctype changes
watch(() => builder.doctype?.name, () => {
  activeTabIndex.value = 0
})

// Clamp active tab index when tabs are removed
watch(() => builder.layout.length, (len) => {
  if (activeTabIndex.value >= len && len > 0) {
    activeTabIndex.value = len - 1
  }
})

function onAddTab() {
  const lastTab = builder.layout[builder.layout.length - 1]
  const afterFieldname = lastTab?._field ? lastTab._fieldname : undefined
  builder.addTab(afterFieldname)
  activeTabIndex.value = builder.layout.length - 1
}

function onRenameTab(fieldname: string, label: string) {
  builder.updateField(fieldname, { label })
}

function onDeleteTab(fieldname: string) {
  builder.removeTab(fieldname)
}

function onReorderTabs(newTabs: LayoutTab[]) {
  // Rebuild flat fields from the reordered layout
  const reorderedLayout = [...newTabs]
  builder.rebuildFlatFields(reorderedLayout)
}

function onUpdateSection(tabIndex: number, sectionIndex: number, updatedSection: LayoutSection) {
  // Section columns changed via drag-and-drop — rebuild flat fields
  const currentLayout = builder.layout.map((tab, ti) => {
    if (ti !== tabIndex) return tab
    return {
      ...tab,
      sections: tab.sections.map((sec, si) => (si === sectionIndex ? updatedSection : sec)),
    }
  })
  builder.rebuildFlatFields(currentLayout)
}

function onDeleteSection(sectionFieldname: string) {
  builder.removeSection(sectionFieldname)
}

function onReorderSections(tabIndex: number, newSections: LayoutSection[]) {
  // Promote any implicit sections so they get a real Section field when serialized
  const promotedSections = newSections.map((section) => {
    if (section._field) return section
    const fieldname = builder.generateFieldname('Section')
    const field = { fieldname, label: section.label, fieldtype: 'Section' as const }
    return { ...section, _fieldname: fieldname, _field: field }
  })
  const newLayout = builder.layout.map((tab, ti) => {
    if (ti !== tabIndex) return tab
    return { ...tab, sections: promotedSections }
  })
  builder.rebuildFlatFields(newLayout)
}

function onAddSection() {
  const currentTab = builder.layout[activeTabIndex.value]
  if (!currentTab) return
  builder.addSection(currentTab._fieldname)
}

function deselect() {
  builder.selectField(null)
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden" @click.self="deselect">
    <!-- Tab bar (always visible, even for single implicit tab) -->
    <CanvasTabBar
      :tabs="builder.layout"
      :active-index="activeTabIndex"
      @update:active-index="activeTabIndex = $event"
      @update:tabs="onReorderTabs"
      @add-tab="onAddTab"
      @rename-tab="onRenameTab"
      @delete-tab="onDeleteTab"
    />

    <!-- All tab contents rendered simultaneously (v-show) so Sortable.js
         keeps its group connections alive during cross-tab drag. -->
    <template v-for="(tab, ti) in builder.layout" :key="tab._fieldname">
      <div
        v-show="ti === activeTabIndex"
        class="flex-1 overflow-y-auto p-4"
        @click.self="deselect"
      >
        <div class="flex flex-col gap-3 max-w-4xl mx-auto">
          <VueDraggable
            :model-value="tab.sections"
            handle=".section-drag-handle"
            ghost-class="opacity-30"
            :animation="200"
            class="flex flex-col gap-3"
            @update:model-value="onReorderSections(ti, $event)"
          >
            <CanvasSection
              v-for="(section, si) in tab.sections"
              :key="section._fieldname"
              :section="section"
              @update:section="onUpdateSection(ti, si, $event)"
              @delete="onDeleteSection(section._fieldname)"
            />
          </VueDraggable>

          <button
            type="button"
            class="flex items-center justify-center gap-1.5 w-full py-2.5 border-2 border-dashed border-border rounded-md text-muted-foreground/70 hover:text-primary hover:border-primary/40 transition-colors"
            @click="onAddSection"
          >
            + Add Section
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
