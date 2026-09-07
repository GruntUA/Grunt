<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { filesApi } from '@/core/api/files'
import { Camera, X, AlertCircle, Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'

defineProps<{ imageOnly: boolean }>()
const emit = defineEmits<{ select: [result: AttachmentResult] }>()

type State = 'idle' | 'starting' | 'live' | 'capturing' | 'uploading' | 'error'

const state = ref<State>('idle')
const error = ref('')
const videoRef = ref<HTMLVideoElement>()
const canvasRef = ref<HTMLCanvasElement>()
let stream: MediaStream | null = null

async function startCamera() {
  error.value = ''
  state.value = 'starting'
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
    })
    state.value = 'live'
    await new Promise<void>(r => setTimeout(r, 50))
    if (videoRef.value) {
      videoRef.value.srcObject = stream
      await videoRef.value.play()
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    error.value = msg.includes('Permission') || msg.includes('NotAllowed')
      ? 'Доступ до камери заборонено. Дозвольте доступ у налаштуваннях браузера.'
      : `Помилка камери: ${msg}`
    state.value = 'error'
    stopStream()
  }
}

function stopStream() {
  stream?.getTracks().forEach(t => t.stop())
  stream = null
  if (state.value !== 'error') state.value = 'idle'
}

async function capture() {
  if (!videoRef.value || !canvasRef.value) return
  state.value = 'capturing'

  const video = videoRef.value
  const canvas = canvasRef.value
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  canvas.getContext('2d')!.drawImage(video, 0, 0)

  stopStream()
  state.value = 'uploading'

  canvas.toBlob(async (blob) => {
    if (!blob) { state.value = 'error'; error.value = 'Не вдалося зробити фото'; return }
    try {
      const file = new File([blob], `capture_${Date.now()}.jpg`, { type: 'image/jpeg' })
      const item = await filesApi.upload(file)
      emit('select', { url: item.url, filename: item.filename, contentType: item.content_type, fileItem: item })
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Помилка завантаження'
      state.value = 'error'
    }
  }, 'image/jpeg', 0.92)
}

onUnmounted(stopStream)
</script>

<template>
  <div class="p-4 flex flex-col items-center gap-4">
    <!-- Idle -->
    <template v-if="state === 'idle' || state === 'error'">
      <div class="flex flex-col items-center gap-3 py-8">
        <Camera class="size-10 text-muted-foreground/40" />
        <p class="text-muted-foreground text-center">Зробіть фото за допомогою камери пристрою</p>
        <Button type="button" @click="startCamera">
          <Camera class="size-4 mr-2" />
          Увімкнути камеру
        </Button>
      </div>
      <div v-if="error" class="flex items-center gap-1.5 text-destructive">
        <AlertCircle class="size-3.5 shrink-0" />
        {{ error }}
      </div>
    </template>

    <!-- Starting -->
    <template v-if="state === 'starting'">
      <div class="flex items-center gap-2 text-muted-foreground py-8">
        <Loader2 class="size-4 animate-spin" />
        Підключення до камери...
      </div>
    </template>

    <!-- Live preview -->
    <template v-if="state === 'live'">
      <div class="relative w-full rounded-lg overflow-hidden bg-black aspect-video max-h-56">
        <video ref="videoRef" class="w-full h-full object-cover" muted playsinline />
      </div>
      <div class="flex gap-2">
        <Button type="button" @click="capture">
          <Camera class="size-4 mr-2" />
          Зробити фото
        </Button>
        <Button variant="outline" type="button" @click="stopStream">
          <X class="size-4 mr-2" />
          Скасувати
        </Button>
      </div>
    </template>

    <!-- Uploading -->
    <template v-if="state === 'uploading' || state === 'capturing'">
      <div class="flex items-center gap-2 text-muted-foreground py-8">
        <Loader2 class="size-4 animate-spin" />
        Завантаження фото...
      </div>
    </template>

    <!-- Hidden canvas for snapshot -->
    <canvas ref="canvasRef" class="hidden" />
  </div>
</template>
