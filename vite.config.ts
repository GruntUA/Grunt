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

// Discover allowed hosts from sites/ directory and their .env files
function discoverAllowedHosts() {
    const hosts = new Set<string>(['localhost', '127.0.0.1'])
    const sitesDir = path.resolve(__dirname, '../../sites')
    if (!fs.existsSync(sitesDir)) return Array.from(hosts)

    for (const siteName of fs.readdirSync(sitesDir)) {
        if (siteName.startsWith('.')) continue
        const sitePath = path.join(sitesDir, siteName)
        if (!fs.statSync(sitePath).isDirectory()) continue

        // Add the directory name itself (e.g. 'itmlt.win')
        hosts.add(siteName)
        hosts.add(`.${siteName}`) // Allow all subdomains

        // Try to read .env for APP_URL
        const envPath = path.join(sitePath, '.env')
        if (fs.existsSync(envPath)) {
            const envContent = fs.readFileSync(envPath, 'utf-8')
            const appUrlMatch = envContent.match(/^APP_URL=https?:\/\/([^/\s]+)/m)
            if (appUrlMatch?.[1]) {
                const host = appUrlMatch[1].split(':')[0]
                hosts.add(host)
                hosts.add(`.${host}`)
            }
        }
    }
    return Array.from(hosts)
}

function isVueVendorModule(id: string): boolean {
    const isVueRouter = id.includes('vue-router')
    const isPinia = id.includes('/pinia/')
    const isCoreVueButNotVueScopedPackage = id.includes('/vue/') && !id.includes('vue-')

    return isVueRouter || isPinia || isCoreVueButNotVueScopedPackage
}

const appAliases = discoverAppAliases()
const allowedHosts = discoverAllowedHosts()

// Match frontend routes that should be proxied to backend clean-URL handling.
// Excludes known Vite/app/API/static prefixes:
// - /app
// - /api
// - /ws
// - /assets
// - /@
// - /node_modules
const CLEAN_URL_PROXY_REGEX = '^(?!(/app($|/)|/api($|/)|/ws($|/)|/assets($|/)|/@|/node_modules|/frontend($|/)|/vite-hmr($|/)))'

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
        host: true,
        allowedHosts: allowedHosts,
        hmr: {
            // When accessed through a reverse proxy / tunnel (e.g. dev2.itmlt.win),
            // tell the browser to connect HMR WebSocket on the standard HTTPS port
            // so the proxy doesn't need to expose port 5173 externally.
            path: 'vite-hmr',
            host: 'dev2.itmlt.win',
            clientPort: 443,
            protocol: 'wss',
        },
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
                    const urlPath = (req.url ?? '').split('?')[0]
                    // Let Vite serve anything with a file extension (source files, manifests, etc.)
                    // Return false to skip the proxy and let Vite handle it natively
                    if (/\.\w+$/.test(urlPath)) return false
                    return undefined
                },
            },
        },
    },
})
