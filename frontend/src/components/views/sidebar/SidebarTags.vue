<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Tag, X, Plus, Loader2 } from '@lucide/vue'
import { docsApi } from '@/core/api/docs'
import type { DocType, GruntDocument } from '@/types'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
}>()

const tags = ref<GruntDocument[]>([])
const tagsLoading = ref(false)
const tagInput = ref('')
const tagAdding = ref(false)

async function loadTags() {
  tagsLoading.value = true
  try {
    tags.value = await docsApi.getTags(props.doctype.name, props.document.id)
  } catch { /* silent */ }
  finally { tagsLoading.value = false }
}

async function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (tags.value.some(t => (t.tag as string)?.toLowerCase() === tag.toLowerCase())) {
    tagInput.value = ''
    return
  }
  tagAdding.value = true
  try {
    const created = await docsApi.addTag(props.doctype.name, props.document.id, tag)
    tags.value = [...tags.value, created]
    tagInput.value = ''
  } catch { /* silent */ }
  finally { tagAdding.value = false }
}

async function removeTag(tag: GruntDocument) {
  try {
    await docsApi.removeTag(tag.id)
    tags.value = tags.value.filter(t => t.id !== tag.id)
  } catch { /* silent */ }
}

function onTagKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    addTag()
  }
}

onMounted(loadTags)
</script>

<template>
  <div class="flex flex-col gap-2 mb-4">
    <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
      <Tag class="size-3.5" />
      Теги
    </span>
    <div class="flex flex-wrap gap-1.5">
      <Badge v-for="t in tags" :key="t.id" severity="contrast" class="text-xs gap-1 pr-1 text-foreground">
        {{ t.tag }}
        <button type="button" class="ml-0.5 rounded-full hover:bg-foreground/10 transition-colors p-0.5"
          @click="removeTag(t)">
          <X class="size-2.5" />
        </button>
      </Badge>
    </div>
    <div class="flex gap-1.5">
      <input v-model="tagInput" placeholder="Додати тег..."
        class="flex-1 h-7 rounded-md border border-input bg-transparent px-2.5 text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
        @keydown="onTagKeydown" />
      <Button outlined class="size-7 text-foreground shrink-0"
        :disabled="!tagInput.trim() || tagAdding" @click="addTag">
        <Loader2 v-if="tagAdding" class="size-3.5 animate-spin" />
        <Plus v-else class="size-3.5" />
      </Button>
    </div>
  </div>
</template>
