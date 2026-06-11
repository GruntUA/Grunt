<script setup lang="ts">
import { computed } from 'vue'
import { User, Clock, ImageIcon } from '@lucide/vue'
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
  return d ? new Date(d).toLocaleDateString('uk-UA', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
})

const modifiedAt = computed(() => {
  const d = props.document.modified_at
  return d ? new Date(d).toLocaleDateString('uk-UA', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
})
</script>

<template>
  <div class="flex flex-col gap-5">
    <!-- Document image -->
    <div v-if="doctype.image_field" class="flex justify-center -mt-1">
      <div v-if="imageUrl" class="size-32 rounded-2xl overflow-hidden ring-4 ring-background shadow-xl border border-border/40">
        <img :src="imageUrl" :alt="document.name" class="size-full object-cover" />
      </div>
      <div v-else class="size-32 rounded-2xl bg-muted/30 border border-dashed border-border flex items-center justify-center">
        <ImageIcon class="size-10 text-muted-foreground/30" />
      </div>
    </div>

    <!-- Meta information -->
    <div class="flex flex-col gap-4 p-4 bg-muted/30 rounded-xl border border-border/40">
      <div class="flex items-center justify-between mb-1">
        <span class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Інформація</span>
        <PresenceAvatars v-if="users" :users="users" :max="3" />
      </div>
      
      <div class="flex flex-col gap-4">
          <div class="flex items-start gap-3">
            <Avatar shape="circle" class="!size-8 !bg-primary/10 !text-primary shrink-0"><User class="size-3.5" /></Avatar>
            <div class="flex flex-col min-w-0">
              <span class="text-sm font-bold text-foreground truncate">{{ document.owner }}</span>
              <span class="text-[10px] font-medium text-muted-foreground">Автор документа</span>
            </div>
          </div>

          <div class="flex items-start gap-3">
            <div class="size-8 rounded-full bg-muted flex items-center justify-center shrink-0">
                <Clock class="size-4 text-muted-foreground" />
            </div>
            <div class="flex flex-col min-w-0">
              <span class="text-sm font-medium text-foreground truncate">{{ createdAt }}</span>
              <span class="text-[10px] font-medium text-muted-foreground uppercase tracking-tighter">Створено</span>
            </div>
          </div>

          <div class="flex items-start gap-3">
            <div class="size-8 rounded-full bg-muted flex items-center justify-center shrink-0">
                <User class="size-4 text-muted-foreground" />
            </div>
            <div class="flex flex-col min-w-0">
              <span class="text-sm font-medium text-foreground truncate">{{ document.modified_by || document.owner }}</span>
              <span class="text-[10px] font-medium text-muted-foreground uppercase tracking-tighter">Остання зміна · {{ modifiedAt }}</span>
            </div>
          </div>
      </div>
    </div>
  </div>
</template>
