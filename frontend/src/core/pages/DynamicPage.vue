<script setup lang="ts">
import { ref, onMounted, shallowRef, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { usePageStore } from '@/stores/pages'
import { resolvePageComponent } from '@/core/pages/registry'
import { Spinner } from '@/components/ui/spinner'

const route = useRoute()
const pageStore = usePageStore()
const component = shallowRef<ReturnType<typeof defineAsyncComponent> | null>(null)
const error = ref('')

onMounted(async () => {
  await pageStore.loadAll()
  const pageDef = pageStore.pages.find((p) => p.route === route.path)
  if (!pageDef) {
    error.value = `Сторінку "${route.path}" не зареєстровано`
    return
  }

  const loader = resolvePageComponent(pageDef.component ?? '')
  if (!loader) {
    error.value = `Компонент "${pageDef.component}" не знайдено. Перевірте що файл існує в src/apps/`
    return
  }

  component.value = defineAsyncComponent(loader as () => Promise<{ default: unknown }>)
})
</script>

<template>
  <div v-if="error" class="p-8 text-center">
    <p class="text-destructive">{{ error }}</p>
  </div>
  <div v-else-if="!component" class="flex justify-center py-16">
    <Spinner class="size-10!" />
  </div>
  <component :is="component" v-else />
</template>
