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

function isVueVendorModule(id: string): boolean {
    const isVueRouter = id.includes('vue-router')
    const isPinia = id.includes('/pinia/')
    const isCoreVueButNotVueScopedPackage = id.includes('/vue/') && !id.includes('vue-')

    return isVueRouter || isPinia || isCoreVueButNotVueScopedPackage
}

const appAliases = discoverAppAliases()

// Match frontend routes that should be proxied to backend clean-URL handling.
// Excludes known Vite/app/API/static prefixes:
// - /app
// - /api
// - /ws
// - /assets
// - /@
// - /node_modules
const CLEAN_URL_PROXY_REGEX = '^(?!(/app($|/)|/api($|/)|/ws($|/)|/assets($|/)|/@|/node_modules))'

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
                    if (isVueVendorModule(id)) return 'vendor-vue'
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
                ws: true,
            },
            // REST API
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            // Static assets from app public/ directories
            '/assets': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            // Public www pages: proxy clean URLs (no file extension) to backend
            [CLEAN_URL_PROXY_REGEX]: {
                target: 'http://localhost:8000',
                changeOrigin: true,
                bypass(req) {
                    const url = (req.url ?? '').split('?')[0]
                    // Let Vite serve anything with a file extension (source files, manifests, etc.)
                    if (/\.\w+$/.test(url)) return url
                    return undefined
                },
            },
        },
    },
})
