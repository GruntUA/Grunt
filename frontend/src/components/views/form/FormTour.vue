<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import type { FormTour } from '@/core/api/workspace'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

/** One form tour: a spotlight on each step's field (or element) and a card that explains it. */
const props = defineProps<{ tour: FormTour; reveal: (fieldname: string) => void }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const titleId = useId()
const index = ref(0)
const rect = ref<DOMRect | null>(null)
const viewport = ref({ width: window.innerWidth, height: window.innerHeight })
const cardEl = ref<HTMLElement | null>(null)
const cardHeight = ref(0)
let target: HTMLElement | null = null

const step = computed(() => props.tour.steps[index.value])
const last = computed(() => index.value === props.tour.steps.length - 1)

const PAD = 6 // spotlight around the target
const GAP = 12 // between the spotlight and the card
const MARGIN = 16 // from the viewport edges
const CARD_WIDTH = 360

function findTarget(): HTMLElement | null {
  const { fieldname, element } = step.value
  const selector = fieldname ? `[data-fieldname="${CSS.escape(fieldname)}"]` : element
  if (!selector) return null
  try {
    return document.querySelector<HTMLElement>(selector)
  } catch {
    return null // not a valid selector
  }
}

function measure() {
  viewport.value = { width: window.innerWidth, height: window.innerHeight }
  const r = target?.getBoundingClientRect()
  rect.value = r && (r.width || r.height) ? r : null
  cardHeight.value = cardEl.value?.offsetHeight ?? 0
}

async function show() {
  const { fieldname } = step.value
  if (fieldname) props.reveal(fieldname)
  // The fields of a tab that has just opened render a few frames later.
  target = null
  for (let i = 0; i < 20 && !target; i++) {
    await nextTick()
    target = findTarget()
    if (!target) await new Promise((resolve) => requestAnimationFrame(resolve))
  }
  target?.scrollIntoView({ block: 'center', behavior: 'instant' })
  measure()
  await nextTick()
  measure()
  cardEl.value?.focus()
}

function go(delta: number) {
  index.value = Math.min(Math.max(index.value + delta, 0), props.tour.steps.length - 1)
}

watch(index, () => void show())

let frame = 0
function onViewportChange() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(measure)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowRight') last.value ? emit('close') : go(1)
  else if (e.key === 'ArrowLeft') go(-1)
  else return
  e.preventDefault()
  e.stopPropagation()
}

onMounted(() => {
  window.addEventListener('resize', onViewportChange)
  window.addEventListener('scroll', onViewportChange, true)
  void show()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
})

const spotlightStyle = computed(() => {
  const r = rect.value
  if (!r) return {}
  return {
    top: `${r.top - PAD}px`,
    left: `${r.left - PAD}px`,
    width: `${r.width + PAD * 2}px`,
    height: `${r.height + PAD * 2}px`,
  }
})

// Below the target when it fits, else above; centred when there is no target.
const cardStyle = computed(() => {
  const r = rect.value
  const { width: vw, height: vh } = viewport.value
  const width = Math.min(CARD_WIDTH, vw - MARGIN * 2)
  if (!r) return { width: `${width}px`, left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
  const below = r.bottom + PAD + GAP
  const above = r.top - PAD - GAP - cardHeight.value
  const top = below + cardHeight.value <= vh - MARGIN || above < MARGIN ? below : above
  const left = Math.min(Math.max(r.left - PAD, MARGIN), vw - width - MARGIN)
  return { width: `${width}px`, left: `${left}px`, top: `${Math.min(top, vh - cardHeight.value - MARGIN)}px` }
})
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50" @keydown="onKeydown">
      <div v-if="rect"
        class="pointer-events-none fixed rounded-md shadow-[0_0_0_9999px_rgb(0_0_0/0.5)] transition-all duration-200"
        :style="spotlightStyle" />
      <div v-else class="fixed inset-0 bg-black/50" />

      <div ref="cardEl" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1"
        class="fixed outline-none transition-[top,left] duration-200" :style="cardStyle">
        <Card class="gap-3 py-4 shadow-lg">
          <CardHeader class="px-4">
            <CardTitle :id="titleId">{{ step.title }}</CardTitle>
            <CardDescription>{{ t('Step {n} of {total}', { n: index + 1, total: tour.steps.length }) }}</CardDescription>
            <CardAction>
              <Button variant="ghost" size="icon-sm" :aria-label="t('Close')" @click="emit('close')"><X /></Button>
            </CardAction>
          </CardHeader>
          <CardContent v-if="step.description" class="px-4 text-sm whitespace-pre-line">
            {{ step.description }}
          </CardContent>
          <CardFooter class="gap-2 px-4">
            <span class="min-w-0 flex-1 truncate text-xs text-muted-foreground">{{ tour.title }}</span>
            <Button v-if="index > 0" variant="ghost" size="sm" @click="go(-1)">{{ t('Back') }}</Button>
            <Button size="sm" @click="last ? emit('close') : go(1)">{{ last ? t('Finish') : t('Next') }}</Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  </Teleport>
</template>
