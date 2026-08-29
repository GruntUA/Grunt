<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const SVG_W = 800
const SVG_H = 200

type Point = [number, number]

const svgRef = ref<SVGSVGElement | null>(null)
const strokes = ref<Point[][]>([])
const currentStroke = ref<Point[]>([])
const isDrawing = ref(false)

const isReadonly = computed(() => props.disabled || props.field.read_only)
const existingValue = computed(() => typeof props.modelValue === 'string' && props.modelValue ? props.modelValue : null)

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
  const paths = strokes.value
    .map((pts) => `<path d="${toPathD(pts)}"/>`)
    .join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SVG_W} ${SVG_H}" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
  emit('update:modelValue', svg)
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
      v-if="existingValue"
      class="rounded-md border border-border overflow-hidden bg-background p-2 h-32 [&>svg]:block [&>svg]:h-full"
      v-html="existingValue"
    />
    <div
      v-else
      class="h-20 rounded-md border border-border flex items-center justify-center text-muted-foreground/50"
    >
      — не підписано —
    </div>
  </div>

  <!-- Editable -->
  <div v-else class="flex flex-col gap-1.5">
    <div
      class="relative rounded-md border overflow-hidden bg-background"
      :class="error ? 'border-destructive' : 'border-input'"
    >
      <!-- Show saved signature with option to re-sign -->
      <template v-if="existingValue && !strokes.length && !currentStroke.length">
        <div class="p-2 h-32 [&>svg]:block [&>svg]:h-full" v-html="existingValue" />
        <button
          type="button"
          class="absolute top-1.5 right-1.5 px-2 py-0.5 text-xs rounded bg-background/90 border border-border text-muted-foreground hover:text-destructive hover:border-destructive transition-colors"
          @click="clear"
        >Очистити</button>
      </template>

      <!-- Drawing canvas -->
      <template v-else>
        <svg
          ref="svgRef"
          :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
          class="w-full h-32 block touch-none cursor-crosshair"
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
          <!-- Baseline -->
          <line :x1="SVG_W * 0.05" :y1="SVG_H * 0.82" :x2="SVG_W * 0.95" :y2="SVG_H * 0.82"
            stroke-dasharray="4 6" class="stroke-muted-foreground/20" stroke-width="1" />

          <!-- Committed strokes -->
          <path v-for="(pts, i) in strokes" :key="i" :d="toPathD(pts)" />

          <!-- Current stroke (live) -->
          <path v-if="currentStroke.length > 1" :d="toPathD(currentStroke)" />
        </svg>

        <div
          v-if="!strokes.length && !currentStroke.length"
          class="pointer-events-none absolute inset-0 flex items-end justify-center pb-8 text-muted-foreground/35 select-none"
        >
          Підпишіть тут
        </div>

        <button
          v-if="strokes.length"
          type="button"
          class="absolute top-1.5 right-1.5 px-2 py-0.5 text-xs rounded bg-background/90 border border-border text-muted-foreground hover:text-destructive hover:border-destructive transition-colors"
          @click="clear"
        >Очистити</button>
      </template>
    </div>
    <p v-if="error" class="text-xs text-destructive">{{ error }}</p>
  </div>
</template>
