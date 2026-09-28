<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed } from 'vue'
import type { AttachmentResult, AttachChannelProps } from '@/core/attachmentChannels/types'
import { AlertCircle } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const { t } = useI18n()

const props = defineProps<AttachChannelProps>()
const emit = defineEmits<{ select: [result: AttachmentResult] }>()

const urlInput = ref('')
const error = ref('')

const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.avif']

const isImageUrl = computed(() => {
  const lower = urlInput.value.toLowerCase()
  return imageExtensions.some(ext => lower.includes(ext))
})

const showImageWarning = computed(() =>
  props.imageOnly && urlInput.value.trim() && !isImageUrl.value
)

function confirm() {
  error.value = ''
  const raw = urlInput.value.trim()
  if (!raw) {
    error.value = t('Enter a URL')
    return
  }
  try {
    const parsed = new URL(raw)
    const filename = parsed.pathname.split('/').filter(Boolean).pop() ?? raw
    emit('select', { url: raw, filename })
  } catch {
    error.value = t('Invalid URL')
  }
}
</script>

<template>
  <div class="p-4 flex flex-col gap-3">
    <p class="text-muted-foreground">{{ t('Enter a direct link to a file on the internet.') }}</p>

    <Input
      v-model="urlInput"
      placeholder="https://example.com/file.pdf"
      class="w-full"
      @keydown.enter="confirm"
    />

    <div v-if="error" class="flex items-center gap-1.5 text-destructive">
      <AlertCircle class="size-3.5 shrink-0" />
      {{ error }}
    </div>

    <div v-if="showImageWarning" class="flex items-center gap-1.5 text-amber-600">
      <AlertCircle class="size-3.5 shrink-0" />
      {{ t('The URL does not look like an image') }}
    </div>

    <Button type="button" :disabled="!urlInput.trim()" @click="confirm">{{ t('Confirm') }}</Button>
  </div>
</template>
