<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBuilderStore } from '@/stores/builder'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-vue-next'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'

const props = defineProps<{ doctype: string }>()
const router = useRouter()
const builder = useBuilderStore()

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
      >&larr; App Studio</button>
      <div class="w-px h-4 bg-[--grunt-border]" />
      <span class="text-sm font-semibold text-[--grunt-text-primary]">
        {{ builder.doctype?.label ?? props.doctype }}
        <span v-if="builder.isDirty" class="text-[--grunt-text-muted] font-normal ml-1">&bull;</span>
      </span>
      <div class="ml-auto flex gap-2">
        <Button size="sm" :disabled="builder.isSaving || !builder.isDirty" @click="builder.save()"><Loader2 v-if="builder.isSaving" class="size-4 animate-spin" />Save</Button>
      </div>
    </div>

    <!-- 3-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Palette (240px) -->
      <div class="w-60 shrink-0">
        <FieldPalette />
      </div>

      <!-- Canvas (WYSIWYG) -->
      <div class="flex-1 overflow-hidden bg-[--grunt-surface-secondary]">
        <BuilderCanvas />
      </div>

      <!-- Properties (300px) -->
      <div class="w-72 shrink-0">
        <PropertiesPanel />
      </div>
    </div>
  </div>
</template>
