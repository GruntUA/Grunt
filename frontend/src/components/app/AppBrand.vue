<script setup lang="ts">
/**
 * App brand mark — the configured `app_logo` image when set, otherwise the
 * Sprout glyph — plus the `app_name`. Single source for the ~5 places that
 * used to hard-code "Ґрунт" / "Grunt Framework" + <Sprout>.
 */
import { Sprout } from '@lucide/vue'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import { cn } from '@/lib/utils'

withDefaults(
  defineProps<{
    showName?: boolean
    /** classes for the icon/logo box */
    markClass?: string
    /** classes for the glyph / img itself */
    glyphClass?: string
    /** classes for the name text */
    nameClass?: string
  }>(),
  { showName: true },
)

const { appName, appLogo } = useSiteConfig()
</script>

<template>
  <span class="flex items-center gap-2">
    <span
      :class="cn(
        'bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-md overflow-hidden',
        markClass,
      )"
    >
      <img
        v-if="appLogo"
        :src="appLogo"
        :alt="appName"
        :class="cn('size-full object-contain', glyphClass)"
      />
      <Sprout v-else :class="cn('size-4', glyphClass)" />
    </span>
    <span v-if="showName" :class="cn('text-foreground font-medium', nameClass)">{{ appName }}</span>
  </span>
</template>
