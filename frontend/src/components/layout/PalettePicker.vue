<script setup lang="ts">
import { useTheme } from '@/core/composables/useTheme'
import { useAuthStore } from '@/stores/auth'
import { Check } from '@lucide/vue'

const { currentPrimary, availableColors, setPrimaryColor } = useTheme()
const auth = useAuthStore()

async function selectColor(colorName: string) {
  setPrimaryColor(colorName)
  await auth.setPrimaryColor(colorName)
}
</script>

<template>
  <div class="p-2">
    <div class="grid grid-cols-5 gap-2">
      <button
        v-for="color in availableColors"
        :key="color.value"
        class="group relative flex size-8 items-center justify-center rounded-full transition-all hover:scale-110 active:scale-95 shadow-sm"
        :style="{ backgroundColor: color.color }"
        :title="color.name"
        @click="selectColor(color.value)"
      >
        <Check
          v-if="currentPrimary === color.value"
          class="size-4 text-white drop-shadow-md animate-in zoom-in duration-200"
        />
        <div class="absolute inset-0 rounded-full ring-2 ring-primary ring-offset-2 opacity-0 group-hover:opacity-40 transition-opacity" />
      </button>
    </div>
  </div>
</template>
