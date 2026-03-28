<script setup lang="ts">
/**
 * Shell for public (unauthenticated) app pages.
 *
 * Route: /public/:app/:page*
 * Resolves component from: src/apps/{app}/pages/{Page}.vue
 *
 * No sidebar, no topbar — just the component full-screen.
 */
import { computed, defineAsyncComponent } from 'vue'
import { resolvePageComponent } from '@/core/pages/registry'

const props = defineProps<{
  app: string
  page?: string | string[]
}>()

const pageName = computed(() => {
  const raw = props.page
  if (!raw) return 'Index'
  const str = Array.isArray(raw) ? raw.join('/') : raw
  // Capitalize first letter: "terminal" → "Terminal", "queue-board" → "QueueBoard"
  return str
    .split(/[-/]/)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('')
})

const componentId = computed(() => `${props.app}/${pageName.value}`)

const resolvedComponent = computed(() => {
  const loader = resolvePageComponent(componentId.value)
  if (!loader) return null
  return defineAsyncComponent(loader)
})
</script>

<template>
  <div class="public-page">
    <component :is="resolvedComponent" v-if="resolvedComponent" />
    <div v-else class="public-page__not-found">
      <p>Сторінку <strong>{{ componentId }}</strong> не знайдено</p>
    </div>
  </div>
</template>

<style scoped>
.public-page {
  min-height: 100vh;
  width: 100%;
}

.public-page__not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  font-size: 1.25rem;
  color: #666;
}
</style>
