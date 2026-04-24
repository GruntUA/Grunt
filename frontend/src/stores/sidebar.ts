import { defineStore } from 'pinia'
import { ref } from 'vue'

const SIDEBAR_COLLAPSED_KEY = 'grunt_sidebar_collapsed'

function getInitialCollapsed(): boolean {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return false
    }
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

function persistCollapsed(value: boolean): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return
    }
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(value))
  } catch {
    // Ignore persistence errors (storage unavailable/blocked)
  }
}

export const useSidebarStore = defineStore('sidebar', () => {
  const isCollapsed = ref(getInitialCollapsed())
  const isMobileVisible = ref(false)

  function toggleCollapse() {
    isCollapsed.value = !isCollapsed.value
    persistCollapsed(isCollapsed.value)
  }

  function setMobileVisible(val: boolean) {
    isMobileVisible.value = val
  }

  function toggleMobile() {
    isMobileVisible.value = !isMobileVisible.value
  }

  return {
    isCollapsed,
    isMobileVisible,
    toggleCollapse,
    setMobileVisible,
    toggleMobile
  }
})
