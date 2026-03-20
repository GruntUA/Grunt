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

    <!-- Preview modal overlay -->
    <Teleport to="body">
      <div
        v-if="isVisible"
        class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
        @click.self="isVisible = false"
      >
        <div class="bg-[--grunt-surface] rounded-[--grunt-radius-lg] shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between p-4 border-b border-[--grunt-border]">
            <h2 class="font-semibold text-[--grunt-text-primary]">Попередній перегляд: {{ builder.doctype?.label }}</h2>
            <button type="button" class="text-[--grunt-text-muted] hover:text-[--grunt-text-primary]" @click="isVisible = false">✕</button>
          </div>
          <div class="p-6">
            <FormRenderer
              v-if="builder.doctype"
              :doctype="builder.doctype"
              :model-value="previewData"
              :disabled="true"
              @update:model-value="previewData = $event"
            />
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
