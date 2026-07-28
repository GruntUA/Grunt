import { ref, watch } from 'vue'

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

// Shade 500 (light mode) / 400 (dark mode) per color — values extracted directly
// from @primevue/themes/aura's `primitive` palette before removing the package,
// so the picker keeps producing pixel-identical colors.
const PALETTE: Record<string, { 500: string; 400: string }> = {
    emerald: { 500: '#10b981', 400: '#34d399' },
    green: { 500: '#22c55e', 400: '#4ade80' },
    lime: { 500: '#84cc16', 400: '#a3e635' },
    orange: { 500: '#f97316', 400: '#fb923c' },
    amber: { 500: '#f59e0b', 400: '#fbbf24' },
    yellow: { 500: '#eab308', 400: '#facc15' },
    teal: { 500: '#14b8a6', 400: '#2dd4bf' },
    cyan: { 500: '#06b6d4', 400: '#22d3ee' },
    sky: { 500: '#0ea5e9', 400: '#38bdf8' },
    blue: { 500: '#3b82f6', 400: '#60a5fa' },
    indigo: { 500: '#6366f1', 400: '#818cf8' },
    violet: { 500: '#8b5cf6', 400: '#a78bfa' },
    purple: { 500: '#a855f7', 400: '#c084fc' },
    fuchsia: { 500: '#d946ef', 400: '#e879f9' },
    pink: { 500: '#ec4899', 400: '#f472b6' },
    rose: { 500: '#f43f5e', 400: '#fb7185' },
}

// Dark-mode contrast color = Aura's default surface palette (zinc) shade 900.
const DARK_CONTRAST = '#18181b'

function applyPrimaryColor(name: string) {
    const scale = PALETTE[name] || PALETTE.indigo
    let styleEl = document.getElementById('primary-color-override') as HTMLStyleElement | null
    if (!styleEl) {
        styleEl = document.createElement('style')
        styleEl.id = 'primary-color-override'
        document.head.appendChild(styleEl)
    }
    styleEl.textContent = [
        `:root { --primary-color-override: ${scale[500]}; --primary-contrast-override: #ffffff; }`,
        `.dark { --primary-color-override: ${scale[400]}; --primary-contrast-override: ${DARK_CONTRAST}; }`,
    ].join('\n')
}

// Singleton state — one ref, one watcher for the entire app lifetime
const stored = localStorage.getItem('grunt_primary_color')
const _current = ref(stored || 'indigo')

watch(_current, (current) => applyPrimaryColor(current), { immediate: true })

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
