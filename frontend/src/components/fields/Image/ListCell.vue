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

const isRounded = computed(() => {
    // Try to intelligently guess if it's an avatar or a square image
    const name = props.field.fieldname.toLowerCase()
    return name.includes('avatar') || name.includes('user') || name.includes('profile')
})
</script>

<template>
    <div class="flex items-center">
        <div v-if="imageUrl" class="relative group/img-cell cursor-pointer">
            <img :src="imageUrl"
                class="size-8 object-cover shadow-sm bg-muted border border-border/40 transition-transform group-hover/img-cell:scale-110"
                :class="isRounded ? 'rounded-full' : 'rounded'"
                @error="(e) => (e.target as HTMLImageElement).src = 'data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'24\' height=\'24\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'currentColor\' stroke-width=\'2\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3E%3Crect width=\'18\' height=\'18\' x=\'3\' y=\'3\' rx=\'2\' ry=\'2\'/%3E%3Ccircle cx=\'9\' cy=\'9\' r=\'2\'/%3E%3Cpath d=\'m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21\'/%3E%3C/svg%3E'" />
        </div>
        <div v-else
            class="size-8 rounded bg-muted/30 flex items-center justify-center border border-dashed border-border/60">
            <ImageIcon class="size-3.5 text-muted-foreground/40" />
        </div>
    </div>
</template>
