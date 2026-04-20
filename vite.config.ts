import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'fs'
import Components from 'unplugin-vue-components/vite'
import { PrimeVueResolver } from '@primevue/auto-import-resolver'

// Discover external app frontend directories (bench/apps/*/www/)
function discoverAppAliases() {
    const aliases: Record<string, string> = {}
    const appsDir = path.resolve(__dirname, '../')
    if (!fs.existsSync(appsDir)) return aliases

    for (const appName of fs.readdirSync(appsDir)) {
        if (appName === 'grunt' || appName.startsWith('.')) continue
        const wwwDir = path.join(appsDir, appName, 'www')
        if (fs.existsSync(wwwDir)) {
            aliases[`@app/${appName}`] = wwwDir
        }
    }
    return aliases
}

const appAliases = discoverAppAliases()

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [
        vue(),
        tailwindcss(),
        Components({
            resolvers: [
                PrimeVueResolver()
            ]
        })
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './frontend/src'),
            ...appAliases,
        },
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (id.includes('primevue') || id.includes('@primevue')) return 'vendor-primevue'
                    if (id.includes('vue-router') || id.includes('/pinia/') || (id.includes('/vue/') && !id.includes('vue-'))) return 'vendor-vue'
                    if (id.includes('@tanstack/vue-query')) return 'vendor-query'
                    if (id.includes('class-variance-authority') || id.includes('/clsx/') || id.includes('tailwind-merge')) return 'vendor-ui'
                    if (id.includes('@lucide/vue')) return 'vendor-icons'
                    if (id.includes('vue-i18n') || id.includes('@intlify')) return 'vendor-i18n'
                    if (id.includes('@codemirror') || id.includes('vue-codemirror') || id.includes('@lezer')) return 'vendor-codemirror'
                    if (id.includes('@tiptap') || id.includes('/tiptap/')) return 'vendor-editor'
                    if (id.includes('chart.js') || id.includes('vue-chartjs')) return 'vendor-charts'
                    if (id.includes('@vue-flow')) return 'vendor-flow'
                },
            },
        },
    },
    server: {
        port: 5173,
        proxy: {
            // WebSocket endpoints — must be listed BEFORE the general /api rule
            '/api/v1/ws': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                ws: true,
            },
            // REST API
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
})
