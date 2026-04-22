import { nextTick, ref, watch, type Ref } from 'vue'
import L from 'leaflet'

export type PrintFormat = 'a4p' | 'a4l' | 'a3p' | 'a3l'

export const PRINT_FORMATS: Record<PrintFormat, { label: string; ratio: number }> = {
  a4p: { label: 'A4 книжна', ratio: 210 / 297 },
  a4l: { label: 'A4 альбомна', ratio: 297 / 210 },
  a3p: { label: 'A3 книжна', ratio: 297 / 420 },
  a3l: { label: 'A3 альбомна', ratio: 420 / 297 },
}

const PRINT_MODE_MAP: Record<PrintFormat, { pageSize: string; orientation: 'Portrait' | 'Landscape' }> = {
  a4p: { pageSize: 'A4', orientation: 'Portrait' },
  a4l: { pageSize: 'A4', orientation: 'Landscape' },
  a3p: { pageSize: 'A3', orientation: 'Portrait' },
  a3l: { pageSize: 'A3', orientation: 'Landscape' },
}

type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w'

interface UseMapPrintParams {
  mapWrapEl: Ref<HTMLDivElement | null>
  getMap: () => L.Map | null
  getBrowserPrint: () => any
}

export function useMapPrint({ mapWrapEl, getMap, getBrowserPrint }: UseMapPrintParams) {
  const isPrintMode = ref(false)
  const printFormat = ref<PrintFormat>('a4p')
  const printRect = ref({ x: 0, y: 0, w: 300, h: 424 })

  let drag: { sx: number; sy: number; ox: number; oy: number } | null = null
  let resize: { handle: Handle; sx: number; sy: number; r0: typeof printRect.value } | null = null

  function initPrintRect() {
    const el = mapWrapEl.value
    if (!el) return
    const cw = el.clientWidth
    const ch = el.clientHeight
    const ratio = PRINT_FORMATS[printFormat.value].ratio
    let w = cw * 0.65
    let h = w / ratio
    if (h > ch * 0.82) {
      h = ch * 0.82
      w = h * ratio
    }
    printRect.value = { x: (cw - w) / 2, y: (ch - h) / 2, w, h }
  }

  watch(printFormat, () => {
    if (!isPrintMode.value || !mapWrapEl.value) return
    const ratio = PRINT_FORMATS[printFormat.value].ratio
    const r = printRect.value
    const cx = r.x + r.w / 2
    const cy = r.y + r.h / 2
    let w = r.w
    let h = w / ratio
    const el = mapWrapEl.value
    if (h > el.clientHeight * 0.95) {
      h = el.clientHeight * 0.95
      w = h * ratio
    }
    printRect.value = { x: cx - w / 2, y: cy - h / 2, w, h }
  })

  function enterPrintMode() {
    isPrintMode.value = true
    nextTick(initPrintRect)
  }

  function cancelPrint() {
    isPrintMode.value = false
  }

  function confirmPrint() {
    const map = getMap()
    const browserPrint = getBrowserPrint()
    if (!map || !browserPrint) return

    const r = printRect.value
    const tl = map.containerPointToLatLng(L.point(r.x, r.y))
    const br = map.containerPointToLatLng(L.point(r.x + r.w, r.y + r.h))
    const bounds = L.latLngBounds(tl, br)

    isPrintMode.value = false

    const LX = L as any
    const onPrintStart = (e: any) => {
      e.printMap.options.zoomSnap = 0
      map.off(LX.BrowserPrint.Event.PrintStart, onPrintStart)
    }
    map.on(LX.BrowserPrint.Event.PrintStart, onPrintStart)

    const { pageSize, orientation } = PRINT_MODE_MAP[printFormat.value]
    const mode = new LX.BrowserPrint.Mode(orientation, {
      pageSize,
      invalidateBounds: true,
    })

    ;(map as any).isPrinting = true
    browserPrint.cancelNextPrinting = false
    browserPrint._print(mode, bounds)
  }

  function startMove(e: MouseEvent) {
    drag = { sx: e.clientX, sy: e.clientY, ox: printRect.value.x, oy: printRect.value.y }
    window.addEventListener('mousemove', onDragMove)
    window.addEventListener('mouseup', stopDrag, { once: true })
    e.preventDefault()
  }

  function onDragMove(e: MouseEvent) {
    if (!drag || !mapWrapEl.value) return
    const el = mapWrapEl.value
    const x = Math.max(0, Math.min(drag.ox + e.clientX - drag.sx, el.clientWidth - printRect.value.w))
    const y = Math.max(0, Math.min(drag.oy + e.clientY - drag.sy, el.clientHeight - printRect.value.h))
    printRect.value = { ...printRect.value, x, y }
  }

  function stopDrag() {
    drag = null
    window.removeEventListener('mousemove', onDragMove)
  }

  function startResize(handle: Handle, e: MouseEvent) {
    resize = { handle, sx: e.clientX, sy: e.clientY, r0: { ...printRect.value } }
    window.addEventListener('mousemove', onResizeMove)
    window.addEventListener('mouseup', stopResize, { once: true })
    e.preventDefault()
    e.stopPropagation()
  }

  const MIN_SIZE = 80

  function onResizeMove(e: MouseEvent) {
    if (!resize || !mapWrapEl.value) return
    const { handle, sx, sy, r0 } = resize
    const el = mapWrapEl.value
    const ratio = PRINT_FORMATS[printFormat.value].ratio
    const dx = e.clientX - sx
    const dy = e.clientY - sy

    let x = r0.x
    let y = r0.y
    let w = r0.w
    let h = r0.h

    if (handle === 'e' || handle === 'ne' || handle === 'se') {
      w = Math.max(MIN_SIZE, r0.w + dx)
      h = w / ratio
    } else if (handle === 'w' || handle === 'nw' || handle === 'sw') {
      w = Math.max(MIN_SIZE, r0.w - dx)
      h = w / ratio
      x = r0.x + r0.w - w
    } else if (handle === 's') {
      h = Math.max(MIN_SIZE, r0.h + dy)
      w = h * ratio
    } else if (handle === 'n') {
      h = Math.max(MIN_SIZE, r0.h - dy)
      w = h * ratio
      y = r0.y + r0.h - h
    }

    if (handle === 'e' || handle === 'w') y = r0.y + r0.h / 2 - h / 2
    if (handle === 'ne' || handle === 'e') y = r0.y + r0.h - h
    if (handle === 'n' || handle === 's') x = r0.x + r0.w / 2 - w / 2

    x = Math.max(0, Math.min(x, el.clientWidth - w))
    y = Math.max(0, Math.min(y, el.clientHeight - h))

    printRect.value = { x, y, w, h }
  }

  function stopResize() {
    resize = null
    window.removeEventListener('mousemove', onResizeMove)
  }

  return {
    isPrintMode,
    printFormat,
    printRect,
    enterPrintMode,
    cancelPrint,
    confirmPrint,
    startMove,
    startResize,
  }
}
