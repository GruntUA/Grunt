import { ref, watch } from 'vue'
import { updatePrimaryPalette } from '@primevue/themes'
import Aura from '@primevue/themes/aura'

export const PRIMARY_COLORS = [
    { name: 'Emerald', value: 'emerald', color: '#10b981' },
    { name: 'Green', value: 'green', color: '#22c55e' },
    { name: 'Lime', value: 'lime', color: '#84cc16' },
    { name: 'Orange', value: 'orange', color: '#f59e0b' },
    { name: 'Amber', value: 'amber', color: '#fbbf24' },
    { name: 'Yellow', value: 'yellow', color: '#facc15' },
    { name: 'Teal', value: 'teal', color: '#14b8a6' },
    { name: 'Cyan', value: 'cyan', color: '#06b6d4' },
    { name: 'Sky', value: 'sky', color: '#0ea5e9' },
    { name: 'Blue', value: 'blue', color: '#3b82f6' },
    { name: 'Indigo', value: 'indigo', color: '#6366f1' },
    { name: 'Violet', value: 'violet', color: '#8b5cf6' },
    { name: 'Purple', value: 'purple', color: '#a855f7' },
    { name: 'Fuchsia', value: 'fuchsia', color: '#d946ef' },
    { name: 'Pink', value: 'pink', color: '#ec4899' },
    { name: 'Rose', value: 'rose', color: '#f43f5e' },
]

// Singleton state — one ref, one watcher for the entire app lifetime
const stored = localStorage.getItem('grunt_primary_color')
const _current = ref(stored || 'indigo')

watch(_current, (current) => {
    try {
        const themePalette = (Aura as any).primitive?.[current] || (Aura as any).primitive?.indigo
        if (themePalette) updatePrimaryPalette(themePalette)
    } catch (e) {
        console.warn('Failed to update primary color:', e)
    }
}, { immediate: true })

export function useTheme() {
    function setPrimaryColor(name: string) {
        _current.value = name
        localStorage.setItem('grunt_primary_color', name)
    }

    return {
        currentPrimary: _current,
        setPrimaryColor,
        availableColors: PRIMARY_COLORS
    }
}
