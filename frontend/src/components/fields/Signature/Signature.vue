<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Undo2 } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const SVG_W = 800
const SVG_H = 200

type Point = [number, number]

const svgRef = ref<SVGSVGElement | null>(null)
const strokes = ref<Point[][]>([])
const currentStroke = ref<Point[]>([])
const isDrawing = ref(false)

const isReadonly = computed(() => props.disabled || props.field.read_only)
const existingValue = computed(() =>
  typeof props.modelValue === 'string' && props.modelValue ? props.modelValue : null,
)

/**
 * Rebuild the stored SVG from a parsed DOM, keeping only our own
 * `<svg><path d="…"/></svg>` shape with numeric path data. Neutralises any
 * markup (event handlers, <script>, foreignObject) a malicious stored value
 * could carry, while keeping `currentColor` so it still follows the theme.
 */
const safeSignature = computed(() => {
  const raw = existingValue.value
  if (!raw || !raw.includes('<svg')) return ''
  const doc = new DOMParser().parseFromString(raw, 'image/svg+xml')
  if (doc.querySelector('parsererror')) return ''
  const src = doc.querySelector('svg')
  if (!src) return ''
  const NS = 'http://www.w3.org/2000/svg'
  const out = document.createElementNS(NS, 'svg')
  out.setAttribute('viewBox', src.getAttribute('viewBox') || `0 0 ${SVG_W} ${SVG_H}`)
  out.setAttribute('width', '100%')
  out.setAttribute('height', '100%')
  out.setAttribute('fill', 'none')
  out.setAttribute('stroke', 'currentColor')
  out.setAttribute('stroke-width', '2.5')
  out.setAttribute('stroke-linecap', 'round')
  out.setAttribute('stroke-linejoin', 'round')
  src.querySelectorAll('path').forEach((p) => {
    const d = p.getAttribute('d')
    if (d && /^[\d\s.,\-mlqcMLQC]+$/.test(d)) {
      const np = document.createElementNS(NS, 'path')
      np.setAttribute('d', d)
      out.appendChild(np)
    }
  })
  return out.outerHTML
})

// Smooth path via midpoint quadratic bezier
function toPathD(pts: Point[]): string {
  if (pts.length < 2) return ''
  if (pts.length === 2) return `M${pts[0][0]},${pts[0][1]}L${pts[1][0]},${pts[1][1]}`
  let d = `M${pts[0][0]},${pts[0][1]}`
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2
    const my = (pts[i][1] + pts[i + 1][1]) / 2
    d += `Q${pts[i][0]},${pts[i][1]},${mx},${my}`
  }
  const last = pts[pts.length - 1]
  d += `L${last[0]},${last[1]}`
  return d
}

function getPos(e: MouseEvent | Touch): Point {
  const svg = svgRef.value!
  const rect = svg.getBoundingClientRect()
  return [
    Math.round(((e.clientX - rect.left) / rect.width) * SVG_W),
    Math.round(((e.clientY - rect.top) / rect.height) * SVG_H),
  ]
}

function addPoint(pt: Point) {
  const last = currentStroke.value.at(-1)
  if (last) {
    const dx = pt[0] - last[0], dy = pt[1] - last[1]
    if (dx * dx + dy * dy < 4) return // skip if < 2px apart
  }
  currentStroke.value.push(pt)
}

function onMouseDown(e: MouseEvent) {
  if (isReadonly.value) return
  isDrawing.value = true
  currentStroke.value = [getPos(e)]
}
function onMouseMove(e: MouseEvent) {
  if (!isDrawing.value) return
  addPoint(getPos(e))
}
function onMouseUp() {
  if (!isDrawing.value) return
  commitStroke()
}

function onTouchStart(e: TouchEvent) {
  if (isReadonly.value) return
  e.preventDefault()
  isDrawing.value = true
  currentStroke.value = [getPos(e.touches[0])]
}
function onTouchMove(e: TouchEvent) {
  if (!isDrawing.value) return
  e.preventDefault()
  addPoint(getPos(e.touches[0]))
}
function onTouchEnd(e: TouchEvent) {
  e.preventDefault()
  if (!isDrawing.value) return
  commitStroke()
}

function commitStroke() {
  isDrawing.value = false
  if (currentStroke.value.length > 1) {
    strokes.value.push([...currentStroke.value])
    save()
  }
  currentStroke.value = []
}

function save() {
  const paths = strokes.value.map((pts) => `<path d="${toPathD(pts)}"/>`).join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SVG_W} ${SVG_H}" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
  emit('update:modelValue', svg)
}

function undo() {
  if (!strokes.value.length) return
  strokes.value.pop()
  if (strokes.value.length) save()
  else emit('update:modelValue', null)
}

function clear() {
  strokes.value = []
  currentStroke.value = []
  emit('update:modelValue', null)
}
</script>

<template>
  <!-- Readonly -->
  <div v-if="isReadonly">
    <div
      v-if="safeSignature"
      role="img"
      :aria-label="field.label"
      class="h-32 overflow-hidden rounded-md border border-border bg-background p-2 [&>svg]:block [&>svg]:h-full"
      v-html="safeSignature"
    />
    <div
      v-else
      class="flex h-20 items-center justify-center rounded-md border border-border text-muted-foreground/50"
    >
      {{ t('Not signed') }}
    </div>
  </div>

  <!-- Editable -->
  <div v-else class="flex flex-col gap-1.5">
    <div
      class="relative overflow-hidden rounded-md border bg-background"
      :class="error ? 'border-destructive' : 'border-input'"
    >
      <!-- Saved signature with option to re-sign -->
      <template v-if="safeSignature && !strokes.length && !currentStroke.length">
        <div class="h-32 p-2 [&>svg]:block [&>svg]:h-full" v-html="safeSignature" />
        <button
          type="button"
          class="absolute right-1.5 top-1.5 rounded border border-border bg-background/90 px-2 py-0.5 text-muted-foreground transition-colors hover:border-destructive hover:text-destructive"
          @click="clear"
        >
          {{ t('Clear') }}
        </button>
      </template>

      <!-- Drawing canvas -->
      <template v-else>
        <svg
          ref="svgRef"
          :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
          role="img"
          :aria-label="field.label"
          class="block h-32 w-full cursor-crosshair touch-none"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
          @touchstart="onTouchStart"
          @touchmove="onTouchMove"
          @touchend="onTouchEnd"
        >
          <line
            :x1="SVG_W * 0.05" :y1="SVG_H * 0.82" :x2="SVG_W * 0.95" :y2="SVG_H * 0.82"
            stroke-dasharray="4 6" class="stroke-muted-foreground/20" stroke-width="1"
          />
          <path v-for="(pts, i) in strokes" :key="i" :d="toPathD(pts)" />
          <path v-if="currentStroke.length > 1" :d="toPathD(currentStroke)" />
        </svg>

        <div
          v-if="!strokes.length && !currentStroke.length"
          class="pointer-events-none absolute inset-0 flex items-end justify-center pb-8 text-muted-foreground/35 select-none"
        >
          {{ t('Sign here') }}
        </div>

        <div v-if="strokes.length" class="absolute right-1.5 top-1.5 flex gap-1">
          <button
            type="button"
            :title="t('Undo')"
            :aria-label="t('Undo')"
            class="rounded border border-border bg-background/90 p-1 text-muted-foreground transition-colors hover:text-foreground"
            @click="undo"
          >
            <Undo2 class="size-3.5" />
          </button>
          <button
            type="button"
            class="rounded border border-border bg-background/90 px-2 py-0.5 text-muted-foreground transition-colors hover:border-destructive hover:text-destructive"
            @click="clear"
          >
            {{ t('Clear') }}
          </button>
        </div>
      </template>
    </div>
    <p v-if="error" class="text-destructive">{{ error }}</p>
  </div>
</template>
