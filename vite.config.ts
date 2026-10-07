import { createLogger, defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'fs'

// Discover external app frontend directories (bench/apps/*/www/)
function discoverAppAliases() {
    const aliases: Record<string, string> = {}
    const appsDir = path.resolve(import.meta.dirname, '../')
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
    const sitesDir = path.resolve(import.meta.dirname, '../../sites')
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

/**
 * Lists every built asset in `precache-manifest.json` so the service worker
 * (public/sw.js) can cache the whole app at install — pages never opened
 * online still work offline.
 */
function precacheManifest(): Plugin {
    return {
        name: 'grunt-precache-manifest',
        apply: 'build',
        generateBundle(_options, bundle) {
            const files = Object.keys(bundle)
                .filter((f) => /\.(js|css|woff2?|svg|png|webp)$/.test(f))
                .map((f) => `/${f}`)
            this.emitFile({ type: 'asset', fileName: 'precache-manifest.json', source: JSON.stringify(files) })
        },
    }
}

/**
 * While the backend is starting or reloading every proxied request fails with
 * ECONNREFUSED and Vite prints a full stack per request. Collapse those into
 * one short line per outage window; other errors pass through untouched.
 */
function quietBackendDownLogger() {
    const logger = createLogger()
    const error = logger.error.bind(logger)
    let lastNotice = 0
    logger.error = (msg, options) => {
        const code = (options?.error as NodeJS.ErrnoException | undefined)?.code
        if (code !== 'ECONNREFUSED') return error(msg, options)
        const now = Date.now()
        if (now - lastNotice > 10_000) {
            lastNotice = now
            logger.warn('backend :8000 is not reachable yet (ECONNREFUSED) - proxied requests fail until it is up', { timestamp: true })
        }
    }
    return logger
}

// https://vitejs.dev/config/
export default defineConfig({
    customLogger: quietBackendDownLogger(),
    plugins: [
        vue(),
        tailwindcss(),
        precacheManifest(),
    ],
    resolve: {
        alias: {
            '@': path.resolve(import.meta.dirname, './frontend/src'),
            ...appAliases,
        },
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks(id) {
                    // Before vendor-vue: these also match its `/vue/` test. `@lucide/vue`
                    // stays auto-split — a manual chunk would pull the full icon set
                    // (lazy-loaded by useLucideIcons) into the initial load.
                    if (id.includes('@lucide/vue')) return
                    if (id.includes('@radix-icons/vue')) return 'vendor-icons'
                    if (isVueVendorModule(id)) return 'vendor-vue'
                    if (id.includes('@tanstack/vue-query')) return 'vendor-query'
                    if (id.includes('/clsx/') || id.includes('tailwind-merge')) return 'vendor-ui'
                    if (id.includes('reka-ui')) return 'vendor-reka'
                    if (id.includes('vue-i18n') || id.includes('@intlify')) return 'vendor-i18n'
                    // CodeMirror runtime core only — the `@codemirror/lang-*` grammars
                    // (and their heavy `@lezer/<language>` parser tables) are dynamically
                    // imported per language in Code.vue, so leave them to auto-splitting.
                    if (
                        id.includes('vue-codemirror')
                        || id.includes('@codemirror/state')
                        || id.includes('@codemirror/view')
                        || id.includes('@codemirror/language')
                        || id.includes('@codemirror/commands')
                        || id.includes('@codemirror/autocomplete')
                        || id.includes('@codemirror/search')
                        || id.includes('@codemirror/lint')
                        || id.includes('@codemirror/theme-one-dark')
                        || id.includes('@lezer/common')
                        || id.includes('@lezer/highlight')
                        || id.includes('@lezer/lr')
                    ) return 'vendor-codemirror'
                    if (id.includes('@tiptap') || id.includes('/tiptap/')) return 'vendor-editor'
                    if (id.includes('chart.js') || id.includes('vue-chartjs')) return 'vendor-charts'
                    if (id.includes('@vue-flow')) return 'vendor-flow'
                },
            },
        },
    },
    define: {
        __VUE_I18N_FULL_INSTALL__: 'true',
        __VUE_I18N_LEGACY_API__: 'false',
        __INTLIFY_JIT_COMPILATION__: 'false',
        __INTLIFY_DROP_MESSAGE_COMPILER__: 'false',
        __INTLIFY_PROD_DEVTOOLS__: 'false',
    },
    optimizeDeps: {
        // vue-i18n must NOT be pre-bundled: the Rolldown-based optimizer in
        // Vite 8 emits a vue-i18n chunk that calls init_runtime_dom_esm_bundler()
        // without importing it ("init_runtime_dom_esm_bundler is not defined").
        // Serving it as plain ESM source avoids the broken chunk.
        exclude: [
            'vue-i18n',
            '@intlify/core-base',
            '@intlify/shared',
            '@intlify/message-compiler',
        ],
    },
    // `vite preview` serves the built dist/ itself — only the API goes to the
    // backend (the dev `server.proxy` would also send /assets there).
    preview: {
        proxy: {
            '/api/v1/ws': { target: 'http://localhost:8000', ws: true },
            '/api': { target: 'http://localhost:8000', changeOrigin: true },
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
                    // Return the path to let Vite serve static files (public/ dir, source files, etc.)
                    // Returning false would produce a 404; returning the path delegates to Vite.
                    if (/\.\w+$/.test(urlPath)) return urlPath
                    return undefined
                },
            },
        },
    },
})
