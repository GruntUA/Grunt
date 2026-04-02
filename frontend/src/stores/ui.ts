import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUIStore = defineStore('ui', () => {
    const isCommandPaletteOpen = ref(false)

    function toggleCommandPalette() {
        isCommandPaletteOpen.value = !isCommandPaletteOpen.value
    }

    function openCommandPalette() {
        isCommandPaletteOpen.value = true
    }

    function closeCommandPalette() {
        isCommandPaletteOpen.value = false
    }

    return {
        isCommandPaletteOpen,
        toggleCommandPalette,
        openCommandPalette,
        closeCommandPalette,
    }
})
