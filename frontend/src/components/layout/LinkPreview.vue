<script setup lang="ts">
/**
 * Link hover card (Frappe "Show Preview Popup").
 *
 * One instance for the whole app: any element carrying
 * `data-preview-doctype` + `data-preview-name` gets a card with the
 * document's title, image and in_preview fields after a short hover - only
 * when the target DocType has `show_preview_popup` on.
 */
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { docsApi, type DocPreview } from '@/core/api/docs'
import { useDocTypeStore } from '@/stores/doctype'
import { getListCell } from '@/core/listCellRegistry'
import { docUrl } from '@/core/workspaceUrl'
import { initials } from '@/core/composables/usePresence'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'
import type { DocField } from '@/types'

const SHOW_DELAY = 700
const HIDE_DELAY = 150
const CACHE_TTL = 60_000
const CARD_WIDTH = 320
const GAP = 6

const doctypeStore = useDocTypeStore()
const router = useRouter()

const preview = shallowRef<DocPreview | null>(null)
const doctype = ref('')
const pos = ref({ top: 0, left: 0 })
const card = ref<HTMLElement | null>(null)

let anchor: HTMLElement | null = null
let showTimer: ReturnType<typeof setTimeout> | undefined
let hideTimer: ReturnType<typeof setTimeout> | undefined
const cache = new Map<string, { at: number; data: Promise<DocPreview | null> }>()

async function enabled(dt: string): Promise<boolean> {
  try {
    return !!(await doctypeStore.get(dt)).show_preview_popup
  } catch {
    return false
  }
}

function load(dt: string, name: string): Promise<DocPreview | null> {
  const key = `${dt}\u0000${name}`
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < CACHE_TTL) return hit.data
  const data = docsApi.getPreview(dt, name).catch(() => null)
  cache.set(key, { at: Date.now(), data })
  return data
}

function place(el: HTMLElement) {
  const r = el.getBoundingClientRect()
  const height = card.value?.offsetHeight ?? 0
  const left = Math.max(8, Math.min(r.left, window.innerWidth - CARD_WIDTH - 8))
  const below = r.bottom + GAP
  const top = below + height > window.innerHeight - 8 && r.top - GAP - height > 8
    ? r.top - GAP - height
    : below
  pos.value = { top, left }
}

function hide() {
  clearTimeout(showTimer)
  clearTimeout(hideTimer)
  anchor = null
  preview.value = null
}

function scheduleHide() {
  clearTimeout(hideTimer)
  hideTimer = setTimeout(hide, HIDE_DELAY)
}

async function show(el: HTMLElement) {
  const dt = el.dataset.previewDoctype ?? ''
  const name = el.dataset.previewName ?? ''
  if (!dt || !name || !(await enabled(dt))) return
  const data = await load(dt, name)
  // The pointer may have moved on (or into a field) while we were loading.
  if (anchor !== el || !data || el.contains(document.activeElement)) return
  doctype.value = dt
  preview.value = data
  place(el)
  requestAnimationFrame(() => anchor === el && place(el))
}

function onPointerOver(e: PointerEvent) {
  if (e.pointerType !== 'mouse') return
  const target = e.target as Element | null
  if (card.value?.contains(target)) {
    clearTimeout(hideTimer)
    return
  }
  const el = target?.closest<HTMLElement>('[data-preview-doctype][data-preview-name]') ?? null
  if (el === anchor) {
    clearTimeout(hideTimer)
    return
  }
  if (!el) {
    if (anchor) scheduleHide()
    return
  }
  clearTimeout(showTimer)
  clearTimeout(hideTimer)
  if (preview.value) preview.value = null
  anchor = el
  showTimer = setTimeout(() => show(el), SHOW_DELAY)
}

function onPointerOut(e: PointerEvent) {
  if (!anchor) return
  const to = e.relatedTarget as Node | null
  if (to && (anchor.contains(to) || card.value?.contains(to))) return
  clearTimeout(showTimer)
  scheduleHide()
}

function onDismiss(e: Event) {
  if (e.type === 'pointerdown' && card.value?.contains(e.target as Node)) return
  if (anchor) hide()
}

function fieldOf(f: DocPreview['fields'][number]): DocField {
  return f as DocField
}

function hasValue(v: unknown): boolean {
  return v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && !v.length)
}

let stopRoute: (() => void) | undefined

onMounted(() => {
  document.addEventListener('pointerover', onPointerOver)
  document.addEventListener('pointerout', onPointerOut)
  document.addEventListener('pointerdown', onDismiss, true)
  document.addEventListener('keydown', onDismiss, true)
  window.addEventListener('scroll', onDismiss, true)
  stopRoute = router.afterEach(hide)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerover', onPointerOver)
  document.removeEventListener('pointerout', onPointerOut)
  document.removeEventListener('pointerdown', onDismiss, true)
  document.removeEventListener('keydown', onDismiss, true)
  window.removeEventListener('scroll', onDismiss, true)
  stopRoute?.()
  hide()
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="preview"
      ref="card"
      role="tooltip"
      class="fixed z-50 w-80 rounded-lg border bg-popover p-4 text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95"
      :style="{ top: `${pos.top}px`, left: `${pos.left}px` }"
    >
      <div class="flex flex-col items-center gap-2 text-center">
        <img v-if="preview.image" :src="preview.image" alt="" class="size-16 rounded-lg object-contain bg-muted/60" />
        <div v-else class="flex size-14 items-center justify-center rounded-full bg-primary/10 text-base font-medium text-primary">
          {{ initials(preview.title) }}
        </div>
        <RouterLink :to="docUrl(doctype, preview.name)" class="text-sm font-semibold hover:underline" @click="hide">
          {{ preview.title }}
        </RouterLink>
        <span v-if="preview.title !== preview.name" class="text-muted-foreground">{{ preview.name }}</span>
      </div>

      <dl v-if="preview.fields.length" class="mt-3 flex flex-col gap-2.5 border-t pt-3">
        <div v-for="f in preview.fields" :key="f.fieldname">
          <dt class="text-muted-foreground">{{ f.label }}</dt>
          <dd class="mt-0.5 break-words">
            <component
              :is="getListCell(f.fieldtype) ?? DefaultListCell"
              v-if="hasValue(preview.row[f.fieldname])"
              :value="preview.row[f.fieldname]"
              :row="preview.row"
              :field="fieldOf(f)"
            />
            <span v-else class="text-muted-foreground/50">—</span>
          </dd>
        </div>
      </dl>
    </div>
  </Teleport>
</template>
