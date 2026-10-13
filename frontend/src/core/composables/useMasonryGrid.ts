import { onBeforeUnmount, watch, type Ref } from 'vue'

const ROW_PX = 4

/**
 * Masonry on a CSS grid: every child spans as many ROW_PX-high rows as its own
 * height (plus the gap) needs, so a short card leaves no hole below it - the
 * next card is placed up into it. Column spans keep working as usual.
 *
 * The grid's row gap is replaced by the span arithmetic; children keep their
 * content height (align-self: start) and are re-measured on every resize.
 */
export function useMasonryGrid(container: Ref<HTMLElement | null | undefined>) {
  const resize = new ResizeObserver((entries) => {
    for (const e of entries) fit(e.target as HTMLElement)
  })
  const children = new MutationObserver(observeChildren)

  function fit(el: HTMLElement) {
    const grid = container.value
    if (!grid) return
    const gap = parseFloat(getComputedStyle(grid).columnGap) || 0
    el.style.alignSelf = 'start'
    el.style.gridRowEnd = `span ${Math.ceil((el.offsetHeight + gap) / ROW_PX)}`
  }

  function observeChildren() {
    resize.disconnect()
    for (const el of Array.from(container.value?.children ?? [])) resize.observe(el)
  }

  watch(container, (grid) => {
    children.disconnect()
    resize.disconnect()
    if (!grid) return
    grid.style.gridAutoRows = `${ROW_PX}px`
    grid.style.rowGap = '0'
    children.observe(grid, { childList: true })
    observeChildren()
  }, { immediate: true, flush: 'post' })

  onBeforeUnmount(() => {
    children.disconnect()
    resize.disconnect()
  })
}
