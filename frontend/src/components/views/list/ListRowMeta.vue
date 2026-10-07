<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { MessageCircle, Heart } from '@lucide/vue'
import type { ListBadge } from '@/core/api/docs'
import { formatAge, formatFull } from '@/core/datetime'

/** Frappe-style row tail: age of the last change · comments · like. */
defineProps<{
  modifiedAt: unknown
  badge?: ListBadge
}>()

const emit = defineEmits<{ like: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="flex items-center justify-end gap-3 whitespace-nowrap text-muted-foreground tabular-nums">
    <time :datetime="(modifiedAt as string | null) ?? undefined" :title="t('Last updated') + ': ' + formatFull(modifiedAt as string | null)">
      {{ formatAge(modifiedAt as string | null) }}
    </time>
    <span class="inline-flex items-center gap-1" :class="!badge?.comments && 'opacity-50'" :title="t('Comments')">
      <MessageCircle class="size-3.5" />{{ badge?.comments ?? 0 }}
    </span>
    <button type="button" class="inline-flex items-center gap-1 hover:text-foreground"
      :class="badge?.liked ? 'text-destructive hover:text-destructive' : !badge?.likes && 'opacity-50 hover:opacity-100'"
      :aria-pressed="!!badge?.liked" :title="badge?.liked ? t('Unlike') : t('Like')" @click.stop.prevent="emit('like')">
      <Heart class="size-3.5" :class="badge?.liked && 'fill-current'" />
      <span v-if="badge?.likes">{{ badge.likes }}</span>
    </button>
  </div>
</template>
