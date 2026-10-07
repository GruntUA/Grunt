<script setup lang="ts">
/**
 * A photo from the webcam (getUserMedia): live preview → «Take photo» →
 * look at it → «Save» or «Retake». Switches between cameras when there are
 * several. Emits the photo as a JPEG `File`.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertCircle, Camera, Check, RefreshCw, SwitchCamera, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

const emit = defineEmits<{ capture: [file: File]; close: [] }>()

const { t } = useI18n()

const video = ref<HTMLVideoElement | null>(null)
const state = ref<'starting' | 'live' | 'taken' | 'error'>('starting')
const error = ref('')
const cameras = ref<MediaDeviceInfo[]>([])
const cameraIndex = ref(0)
const photo = ref<{ blob: Blob; url: string } | null>(null)
let stream: MediaStream | null = null

const canSwitch = computed(() => cameras.value.length > 1)

async function start() {
  stop()
  state.value = 'starting'
  error.value = ''
  try {
    const deviceId = cameras.value[cameraIndex.value]?.deviceId
    stream = await navigator.mediaDevices.getUserMedia({
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
        : { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    })
    // Labels and the full list are only there once access was granted.
    if (!cameras.value.length) {
      cameras.value = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput')
      const active = stream.getVideoTracks()[0]?.getSettings().deviceId
      cameraIndex.value = Math.max(0, cameras.value.findIndex((c) => c.deviceId === active))
    }
    state.value = 'live'
    await nextTick()
    if (video.value) {
      video.value.srcObject = stream
      await video.value.play()
    }
  } catch (err) {
    stop()
    const name = (err as { name?: string }).name
    error.value = name === 'NotAllowedError'
      ? t('Camera access denied. Allow access in browser settings.')
      : name === 'NotFoundError'
        ? t('No camera found')
        : t('Camera error: {msg}', { msg: err instanceof Error ? err.message : String(err) })
    state.value = 'error'
  }
}

function stop() {
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
}

function switchCamera() {
  cameraIndex.value = (cameraIndex.value + 1) % cameras.value.length
  start()
}

function take() {
  const v = video.value
  if (!v?.videoWidth) return
  const canvas = document.createElement('canvas')
  canvas.width = v.videoWidth
  canvas.height = v.videoHeight
  canvas.getContext('2d')!.drawImage(v, 0, 0)
  canvas.toBlob((blob) => {
    if (!blob) return
    photo.value = { blob, url: URL.createObjectURL(blob) }
    state.value = 'taken'
    stop()
  }, 'image/jpeg', 0.92)
}

function retake() {
  dropPhoto()
  start()
}

function save() {
  if (!photo.value) return
  const stamp = new Date().toLocaleString('sv-SE').replace(/:/g, '-') // 2026-10-07 14-30-15
  emit('capture', new File([photo.value.blob], `${t('Photo')} ${stamp}.jpg`, { type: 'image/jpeg' }))
}

function dropPhoto() {
  if (photo.value) URL.revokeObjectURL(photo.value.url)
  photo.value = null
}

onMounted(start)
onBeforeUnmount(() => {
  stop()
  dropPhoto()
})
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 bg-muted/30 p-4">
    <div class="relative flex min-h-0 w-full max-w-3xl flex-1 items-center justify-center overflow-hidden rounded-lg bg-black">
      <video v-show="state === 'live'" ref="video" muted playsinline class="max-h-full max-w-full" />
      <img v-if="state === 'taken' && photo" :src="photo.url" :alt="t('Photo')" class="max-h-full max-w-full" />
      <div v-if="state === 'starting'" class="flex items-center gap-2 text-white/80">
        <Spinner />{{ t('Connecting to the camera...') }}
      </div>
      <div v-if="state === 'error'" class="flex max-w-sm flex-col items-center gap-3 p-6 text-center text-white/90">
        <AlertCircle class="size-8" />
        <p>{{ error }}</p>
        <Button variant="secondary" size="sm" @click="start"><RefreshCw />{{ t('Try again') }}</Button>
      </div>
      <Button v-if="state === 'live' && canSwitch" variant="secondary" size="icon"
        class="absolute right-3 top-3 rounded-full" :title="t('Switch camera')" @click="switchCamera">
        <SwitchCamera />
      </Button>
    </div>

    <div class="flex gap-2">
      <template v-if="state === 'taken'">
        <Button variant="outline" @click="retake"><RefreshCw />{{ t('Retake') }}</Button>
        <Button @click="save"><Check />{{ t('Save') }}</Button>
      </template>
      <Button v-else :disabled="state !== 'live'" @click="take"><Camera />{{ t('Take photo') }}</Button>
      <Button variant="ghost" @click="emit('close')"><X />{{ t('Cancel') }}</Button>
    </div>
  </div>
</template>
