<script setup lang="ts">
import { inject, onMounted } from 'vue'

const props = defineProps<{ src?: string; alt?: string }>()

const ctx = inject<{
  setStatus: (s: 'idle' | 'loading' | 'loaded' | 'error') => void
}>('$avatar')

onMounted(() => { if (props.src) ctx?.setStatus('loading') })
</script>

<template>
  <img
    v-if="src"
    data-slot="avatar-image"
    :src="src"
    :alt="alt ?? ''"
    class="aspect-square size-full object-cover"
    @load="ctx?.setStatus('loaded')"
    @error="ctx?.setStatus('error')"
  />
</template>
