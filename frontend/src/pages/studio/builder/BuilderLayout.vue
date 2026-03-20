<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBuilderStore } from '@/stores/builder'
import GButton from '@/components/ui/GButton.vue'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'
import BuilderPreview from './BuilderPreview.vue'

const props = defineProps<{ doctype: string }>()
const router = useRouter()
const builder = useBuilderStore()
const showPreview = ref(false)

onMounted(() => builder.loadDocType(props.doctype))
</script>

<template>
  <div class="flex flex-col h-screen overflow-hidden">
    <!-- Header -->
    <div class="flex items-center gap-4 px-4 py-3 border-b border-[--grunt-border] bg-[--grunt-surface] shrink-0">
      <button
        type="button"
        class="text-sm text-[--grunt-text-secondary] hover:text-[--grunt-primary] transition-colors"
        @click="router.push('/studio')"
      >← App Studio</button>
      <div class="w-px h-4 bg-[--grunt-border]" />
      <span class="text-sm font-semibold text-[--grunt-text-primary]">
        {{ builder.doctype?.label ?? props.doctype }}
        <span v-if="builder.isDirty" class="text-[--grunt-text-muted] font-normal ml-1">●</span>
      </span>
      <div class="ml-auto flex gap-2">
        <GButton variant="secondary" size="sm" @click="showPreview = true">Попередній перегляд</GButton>
        <GButton size="sm" :loading="builder.isSaving" :disabled="!builder.isDirty" @click="builder.save()">Зберегти</GButton>
      </div>
    </div>

    <!-- 3-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Palette (240px) -->
      <div class="w-60 shrink-0">
        <FieldPalette />
      </div>

      <!-- Canvas -->
      <div class="flex-1 overflow-hidden bg-[--grunt-surface-secondary]">
        <BuilderCanvas />
      </div>

      <!-- Properties (300px) -->
      <div class="w-72 shrink-0">
        <PropertiesPanel />
      </div>
    </div>

    <!-- Preview overlay -->
    <Teleport to="body">
      <div
        v-if="showPreview"
        class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
        @click.self="showPreview = false"
      >
        <div class="bg-[--grunt-surface] rounded-[--grunt-radius-lg] shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
          <div class="flex items-center justify-between p-4 border-b border-[--grunt-border]">
            <h2 class="font-semibold text-[--grunt-text-primary]">Попередній перегляд: {{ builder.doctype?.label }}</h2>
            <button type="button" class="text-[--grunt-text-muted] hover:text-[--grunt-text-primary] text-lg" @click="showPreview = false">✕</button>
          </div>
          <div class="p-6">
            <BuilderPreview />
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
