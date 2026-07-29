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
    tags.value = await docsApi.getTags(props.doctype.name, props.document.name)
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
    const created = await docsApi.addTag(props.doctype.name, props.document.name, tag)
    tags.value = [...tags.value, created]
    tagInput.value = ''
  } catch { /* silent */ }
  finally { tagAdding.value = false }
}

async function removeTag(tag: GruntDocument) {
  try {
    await docsApi.removeTag(tag.name)
    tags.value = tags.value.filter(t => t.name !== tag.name)
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
  <div class="flex flex-col gap-3 mb-0 p-3 bg-muted/30 rounded-lg border border-border/40">
    <span class="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5 px-0.5">
      <Tag class="size-3" />
      Теги
    </span>

    <div v-if="tags.length > 0" class="flex flex-wrap gap-2">
      <Badge v-for="t in tags" :key="t.id"
        class="pl-2 pr-2 py-0.5 text-xs font-semibold bg-background border border-border/60 shadow-sm"
      >
        <span class="mr-2">{{ t.tag }}</span>
        <X class="size-3 cursor-pointer hover:text-destructive transition-colors shrink-0" @click="removeTag(t)" />
      </Badge>
    </div>

    <!-- Add tag input -->
    <div class="flex gap-1.5 mt-1">
      <div class="inline-flex h-8 shadow-sm w-full">
        <Input
            v-model="tagInput"
            placeholder="Додати тег..."
            class="!text-xs h-full rounded-r-none flex-1"
            @keydown="onTagKeydown"
        />
        <Button class="h-full px-2 rounded-l-none border-l-0" :disabled="!tagInput.trim() || tagAdding" @click="addTag">
          <Loader2 v-if="tagAdding" class="size-3.5 animate-spin" />
          <Plus v-else class="size-3.5" />
        </Button>
      </div>
    </div>
  </div>
</template>
