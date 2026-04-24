import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSidebarStore = defineStore('sidebar', () => {
  const isCollapsed = ref(localStorage.getItem('grunt_sidebar_collapsed') === 'true')
  const isMobileVisible = ref(false)

  function toggleCollapse() {
    isCollapsed.value = !isCollapsed.value
    localStorage.setItem('grunt_sidebar_collapsed', String(isCollapsed.value))
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
