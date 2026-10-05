<script setup lang="ts">
import { computed } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import { Image as ImageIcon } from '@lucide/vue'

const props = defineProps<{
    value: unknown
    row: Record<string, unknown>
    field: DocField
    statusConfig?: DocTypeStatusConfig | null
}>()

const imageUrl = computed(() => {
    if (!props.value) return null
    return String(props.value)
})

// Avatar-like fields (faces) should fill a circle; everything else is a
// product/thumbnail - keep the whole subject visible on a neutral tile.
const isAvatar = computed(() => {
    const name = props.field.fieldname.toLowerCase()
    return name.includes('avatar') || name.includes('user') || name.includes('profile')
})

const FALLBACK_SVG =
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='18' height='18' x='3' y='3' rx='2' ry='2'/%3E%3Ccircle cx='9' cy='9' r='2'/%3E%3Cpath d='m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21'/%3E%3C/svg%3E"
</script>

<template>
    <div class="flex items-center">
        <img v-if="imageUrl" :src="imageUrl" alt="" loading="lazy" decoding="async"
            class="size-11 shrink-0 bg-muted/60 ring-1 ring-border/60 transition-shadow hover:ring-primary/40 hover:shadow-md"
            :class="isAvatar ? 'rounded-full object-cover' : 'rounded-lg object-contain p-0.5'"
            @error="(e) => { const t = e.target as HTMLImageElement; if (t.src !== FALLBACK_SVG) t.src = FALLBACK_SVG }" />
        <div v-else
            class="size-11 shrink-0 flex items-center justify-center bg-muted/30 border border-dashed border-border/60"
            :class="isAvatar ? 'rounded-full' : 'rounded-lg'">
            <ImageIcon class="size-4 text-muted-foreground/40" />
        </div>
    </div>
</template>
