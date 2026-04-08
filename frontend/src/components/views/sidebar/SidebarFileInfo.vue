<script setup lang="ts">
import { computed } from 'vue'
import { User, Clock, ImageIcon } from 'lucide-vue-next'
import PresenceAvatars from '@/components/ui/PresenceAvatars.vue'
import type { DocType, GruntDocument } from '@/types'
import type { PresenceUser } from '@/core/composables/usePresence'

const props = defineProps<{
  doctype: DocType
  document: GruntDocument
  users?: PresenceUser[]
}>()

const imageUrl = computed(() => {
  if (!props.doctype.image_field) return null
  const val = props.document[props.doctype.image_field]
  return typeof val === 'string' && val ? val : null
})

const createdAt = computed(() => {
  const d = props.document.created_at
  return d ? new Date(d).toLocaleString('uk-UA') : '—'
})

const modifiedAt = computed(() => {
  const d = props.document.modified_at
  return d ? new Date(d).toLocaleString('uk-UA') : '—'
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- Document image -->
    <div v-if="doctype.image_field" class="flex justify-center mb-1">
      <div v-if="imageUrl" class="size-28 rounded-xl overflow-hidden ring-1 ring-border/60 shadow-sm">
        <img :src="imageUrl" :alt="document.name" class="size-full object-cover" />
      </div>
      <div v-else class="size-28 rounded-xl bg-muted/50 ring-1 ring-border/40 flex items-center justify-center">
        <ImageIcon class="size-8 text-muted-foreground/40" />
      </div>
    </div>

    <!-- Meta information -->
    <div class="flex flex-col gap-3 text-sm">
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Інформація</span>
        <PresenceAvatars v-if="users" :users="users" :max="3" />
      </div>
      <div class="flex items-start gap-2.5">
        <User class="size-4 text-muted-foreground shrink-0 mt-0.5" />
        <div>
          <div class="text-foreground">{{ document.owner }}</div>
          <div class="text-xs text-muted-foreground">Автор</div>
        </div>
      </div>
      <div class="flex items-start gap-2.5">
        <Clock class="size-4 text-muted-foreground shrink-0 mt-0.5" />
        <div>
          <div class="text-foreground">{{ createdAt }}</div>
          <div class="text-xs text-muted-foreground">Створено</div>
        </div>
      </div>
      <div v-if="document.modified_by && document.modified_by !== document.owner" class="flex items-start gap-2.5">
        <User class="size-4 text-muted-foreground shrink-0 mt-0.5" />
        <div>
          <div class="text-foreground">{{ document.modified_by }}</div>
          <div class="text-xs text-muted-foreground">Змінив · {{ modifiedAt }}</div>
        </div>
      </div>
      <div v-else class="flex items-start gap-2.5">
        <Clock class="size-4 text-muted-foreground shrink-0 mt-0.5" />
        <div>
          <div class="text-foreground">{{ modifiedAt }}</div>
          <div class="text-xs text-muted-foreground">Останнє редагування</div>
        </div>
      </div>
    </div>
  </div>
</template>
