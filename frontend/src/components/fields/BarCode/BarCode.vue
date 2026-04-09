<script setup lang="ts">
/**
 * FieldBarcode — barcode / QR-code scanner field.
 *
 * Input modes:
 *  1. Manual text input (always available)
 *  2. Camera scan via BarcodeDetector API (native or polyfill)
 *  3. File upload — user picks an image; decoded via BarcodeDetector
 *
 * On platforms where the native BarcodeDetector is unavailable (Windows desktop),
 * the `barcode-detector` npm polyfill (ZXing-WASM) is loaded dynamically.
 */
import { ref, onMounted, onUnmounted } from 'vue'
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ScanLine, Upload, X, CheckCircle2, AlertCircle } from 'lucide-vue-next'

type BarcodeDetectorInstance = {
  detect(source: ImageBitmapSource): Promise<Array<{ rawValue: string; format: string }>>
}
type BarcodeDetectorClass = {
  new(opts?: { formats?: string[] | readonly string[] }): BarcodeDetectorInstance
  getSupportedFormats(): Promise<readonly string[]>
}

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

// ── State ──────────────────────────────────────────────────────────────────

const scanning = ref(false)
const scanError = ref('')
const scanSuccess = ref(false)
const videoRef = ref<HTMLVideoElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

let BarcodeDetectorCtor: BarcodeDetectorClass | null = null
let stream: MediaStream | null = null
let rafId: number | null = null
let detector: BarcodeDetectorInstance | null = null

// ── Polyfill bootstrap ─────────────────────────────────────────────────────

async function ensureDetector(): Promise<BarcodeDetectorClass | null> {
  if (BarcodeDetectorCtor) return BarcodeDetectorCtor

  // Native API (Android Chrome/Edge, macOS, Safari 17+)
  if ('BarcodeDetector' in window) {
    BarcodeDetectorCtor = (window as unknown as { BarcodeDetector: BarcodeDetectorClass }).BarcodeDetector
    return BarcodeDetectorCtor
  }

  // Polyfill (Windows Chrome/Edge, Firefox)
  try {
    const mod = await import('barcode-detector')
    // The package exports a named `BarcodeDetector` class, not a default export
    const Ctor = mod.BarcodeDetector as unknown as BarcodeDetectorClass
    // Install into window so future calls skip this block
    ;(window as unknown as { BarcodeDetector?: BarcodeDetectorClass }).BarcodeDetector = Ctor
    BarcodeDetectorCtor = Ctor
    return BarcodeDetectorCtor
  } catch {
    return null
  }
}

onMounted(async () => {
  // Pre-warm the polyfill so first scan is instant
  await ensureDetector()
})

// ── Camera scan ────────────────────────────────────────────────────────────

async function startScan() {
  scanError.value = ''
  scanSuccess.value = false

  const Ctor = await ensureDetector()
  if (!Ctor) {
    scanError.value = 'Сканування не підтримується у цьому браузері. Скористайтесь завантаженням зображення.'
    return
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    scanError.value = 'Камера недоступна.'
    return
  }

  try {
    const formats = await Ctor.getSupportedFormats()
    detector = new Ctor({ formats })

    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
    })
    scanning.value = true

    await new Promise<void>(resolve => setTimeout(resolve, 50))

    if (videoRef.value) {
      videoRef.value.srcObject = stream
      await videoRef.value.play()
      detectLoop()
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    scanError.value = msg.includes('Permission') || msg.includes('NotAllowed')
      ? 'Доступ до камери заборонено. Дозвольте доступ у налаштуваннях браузера.'
      : `Помилка камери: ${msg}`
    stopScan()
  }
}

function detectLoop() {
  if (!videoRef.value || !detector) return
  rafId = requestAnimationFrame(async () => {
    try {
      if (videoRef.value && videoRef.value.readyState >= 2) {
        const results = await detector!.detect(videoRef.value)
        if (results.length > 0) {
          onDecoded(results[0].rawValue)
          return
        }
      }
    } catch {
      // detector may throw on some frames — just continue
    }
    if (scanning.value) detectLoop()
  })
}

function stopScan() {
  if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  scanning.value = false
}

function onDecoded(value: string) {
  stopScan()
  emit('update:modelValue', value)
  scanSuccess.value = true
  setTimeout(() => { scanSuccess.value = false }, 2000)
}

// ── File upload fallback ───────────────────────────────────────────────────

async function onFileChange(e: Event) {
  scanError.value = ''
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return

  const Ctor = await ensureDetector()
  if (!Ctor) {
    scanError.value = 'Сканування не підтримується у цьому браузері.'
    return
  }

  try {
    const bitmap = await createImageBitmap(file)
    const formats = await Ctor.getSupportedFormats()
    const det = new Ctor({ formats })
    const results = await det.detect(bitmap)
    bitmap.close()

    if (results.length > 0) {
      onDecoded(results[0].rawValue)
    } else {
      scanError.value = 'Штрих-код не знайдено на зображенні.'
    }
  } catch (err: unknown) {
    scanError.value = `Помилка: ${err instanceof Error ? err.message : String(err)}`
  }

  if (fileInputRef.value) fileInputRef.value.value = ''
}

// ── Cleanup ────────────────────────────────────────────────────────────────

onUnmounted(stopScan)
</script>

<template>
  <div class="space-y-2">
    <!-- Text input + action buttons -->
    <div class="flex gap-2">
      <div class="relative flex-1">
        <Input
          :model-value="String(modelValue ?? '')"
          :placeholder="field.placeholder ?? 'Відскануйте або введіть вручну'"
          :required="field.required"
          :disabled="disabled || field.read_only"
          class="pr-8"
          @update:model-value="emit('update:modelValue', $event)"
        />
        <CheckCircle2
          v-if="scanSuccess"
          class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-green-500 animate-in fade-in"
        />
      </div>

      <!-- Camera scan button -->
      <Button
        v-if="!scanning"
        type="button"
        variant="outline"
        size="icon"
        :disabled="disabled || field.read_only"
        title="Сканувати камерою"
        @click="startScan"
      >
        <ScanLine class="w-4 h-4" />
      </Button>

      <!-- Stop scan -->
      <Button
        v-if="scanning"
        type="button"
        variant="outline"
        size="icon"
        title="Зупинити"
        @click="stopScan"
      >
        <X class="w-4 h-4" />
      </Button>

      <!-- File upload -->
      <Button
        v-if="!scanning"
        type="button"
        variant="outline"
        size="icon"
        :disabled="disabled || field.read_only"
        title="Завантажити зображення зі штрих-кодом"
        @click="fileInputRef?.click()"
      >
        <Upload class="w-4 h-4" />
      </Button>
      <input ref="fileInputRef" type="file" accept="image/*" class="hidden" @change="onFileChange" />
    </div>

    <!-- Camera viewfinder -->
    <div v-if="scanning" class="relative rounded-xl overflow-hidden bg-black aspect-video max-h-64">
      <video ref="videoRef" class="w-full h-full object-cover" muted playsinline />
      <div class="absolute inset-0 pointer-events-none">
        <div class="absolute inset-x-8 top-1/2 h-0.5 bg-primary/70 animate-pulse rounded-full" />
        <div class="absolute top-3 left-3 w-8 h-8 border-t-2 border-l-2 border-primary rounded-tl" />
        <div class="absolute top-3 right-3 w-8 h-8 border-t-2 border-r-2 border-primary rounded-tr" />
        <div class="absolute bottom-3 left-3 w-8 h-8 border-b-2 border-l-2 border-primary rounded-bl" />
        <div class="absolute bottom-3 right-3 w-8 h-8 border-b-2 border-r-2 border-primary rounded-br" />
      </div>
      <p class="absolute bottom-2 inset-x-0 text-center text-[11px] text-white/70">
        Наведіть камеру на штрих-код або QR-код
      </p>
    </div>

    <!-- Error message -->
    <div v-if="scanError || error" class="flex items-center gap-1.5 text-xs text-destructive">
      <AlertCircle class="w-3.5 h-3.5 shrink-0" />
      {{ scanError || error }}
    </div>
  </div>
</template>
