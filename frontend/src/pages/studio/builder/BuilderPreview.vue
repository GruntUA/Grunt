<script setup lang="ts">
import { ref } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import FormRenderer from '@/core/renderer/FormRenderer.vue'

const builder = useBuilderStore()
const previewData = ref<Record<string, unknown>>({})

const isVisible = ref(false)
</script>

<template>
  <div>
    <!-- Toggle button (used from BuilderLayout header) -->
    <slot :toggle="() => { isVisible = !isVisible }" />

    <!-- Preview modal -->
    <Dialog :open="isVisible" @update:open="(v: boolean) => isVisible = v">
      <DialogContent class="max-w-2xl max-h-[90vh] overflow-y-auto p-0">
        <DialogHeader class="p-4 border-b border-border">
          <DialogTitle class="font-semibold">Попередній перегляд: {{ builder.doctype?.label }}</DialogTitle>
        </DialogHeader>
        <div class="p-6">
          <FormRenderer
            v-if="builder.doctype"
            :doctype="builder.doctype"
            :model-value="previewData"
            :disabled="true"
            @update:model-value="previewData = $event"
          />
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
