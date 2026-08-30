/**
 * Positions a teleported dropdown against an anchor element using fixed
 * coordinates, and keeps it glued to the anchor while it is open — the anchor
 * moves under a `position: fixed` layer on any page/container scroll or window
 * resize, so those must trigger a re-measure.
 *
 * Shared by the Link / MultiLink field dropdowns (both teleport to <body> so a
 * scrollable form container can't clip them).
 *
 * The anchor element ref is supplied by the caller so it can be wired with a
 * plain `ref="…"` in the template.
 */
import { onUnmounted, ref, watch, type Ref } from 'vue'

export function useAnchoredDropdown(
  isOpen: Ref<boolean>,
  anchorRef: Ref<HTMLElement | null>,
  opts: { gap?: number; flipMargin?: number } = {},
) {
  const gap = opts.gap ?? 4
  const flipMargin = opts.flipMargin ?? 120

  const dropdownStyle = ref<Record<string, string>>({})

  function reposition() {
    const el = anchorRef.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom - gap
    const openUp = spaceBelow < flipMargin && rect.top > spaceBelow
    dropdownStyle.value = {
      position: 'fixed',
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      zIndex: '9999',
      ...(openUp
        ? { bottom: `${window.innerHeight - rect.top + gap}px` }
        : { top: `${rect.bottom + gap}px` }),
    }
  }

  function onViewportChange() {
    if (isOpen.value) reposition()
  }

  watch(isOpen, (open) => {
    if (open) {
      reposition()
      window.addEventListener('scroll', onViewportChange, true)
      window.addEventListener('resize', onViewportChange)
    } else {
      window.removeEventListener('scroll', onViewportChange, true)
      window.removeEventListener('resize', onViewportChange)
    }
  })

  onUnmounted(() => {
    window.removeEventListener('scroll', onViewportChange, true)
    window.removeEventListener('resize', onViewportChange)
  })

  return { dropdownStyle, reposition }
}
