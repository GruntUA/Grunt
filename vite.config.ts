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

// Vue core packages only, matched by exact package dir. A looser `/vue/` test
// also caught bindings such as `@unovis/vue`, and each group pulls in its
// modules' dependencies - so d3/unovis ended up in the initial vendor-vue chunk.
const VUE_CORE = /\/node_modules\/(vue|@vue\/[^/]+|vue-router|pinia)\//

function isVueVendorModule(id: string): boolean {
    return VUE_CORE.test(id)
}

const CODEMIRROR_CORE = [
    'vue-codemirror',
    '@codemirror/state',
    '@codemirror/view',
    '@codemirror/language',
    '@codemirror/commands',
    '@codemirror/autocomplete',
    '@codemirror/search',
    '@codemirror/lint',
    '@codemirror/theme-one-dark',
    '@lezer/common',
    '@lezer/highlight',
    '@lezer/lr',
]

const appAliases = discoverAppAliases()
// Bench apps/ - apps ship frontend pieces the core discovers by glob (e.g.
// dashboard widgets: @apps/<app>/dashboard_widgets/<Name>/).
const appsDir = path.resolve(import.meta.dirname, '../')
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
        // App frontend pieces (@apps/<app>/desk/…, dashboard_widgets) live
        // outside this package and have no node_modules of their own: their
        // bare imports resolve to the framework's copies.
        dedupe: ['vue', 'vue-router', 'pinia', 'vue-i18n', 'reka-ui', '@lucide/vue'],
        alias: {
            '@': path.resolve(import.meta.dirname, './frontend/src'),
            '@apps': appsDir,
            ...appAliases,
        },
    },
    build: {
        rolldownOptions: {
            output: {
                // Explicit groups rather than `manualChunks`: Rolldown turns that into a
                // single group that also captures each module's dependencies, so the
                // Vue runtime (a dependency of vue-codemirror) landed in
                // vendor-codemirror and every page preloaded CodeMirror. Separate groups
                // are matched in order, and a module taken by an earlier group is
                // removed from the later ones.
                codeSplitting: {
                    groups: [
                        { name: 'vendor-vue', test: isVueVendorModule },
                        { name: 'vendor-query', test: (id) => id.includes('@tanstack/vue-query') },
                        { name: 'vendor-ui', test: (id) => id.includes('/clsx/') || id.includes('tailwind-merge') },
                        { name: 'vendor-reka', test: (id) => id.includes('reka-ui') },
                        { name: 'vendor-i18n', test: (id) => id.includes('vue-i18n') || id.includes('@intlify') },
                        // CodeMirror runtime core only — the `@codemirror/lang-*` grammars
                        // (and their heavy `@lezer/<language>` parser tables) are dynamically
                        // imported per language in CodeEditor.vue, so leave them to auto-splitting.
                        { name: 'vendor-codemirror', test: (id) => CODEMIRROR_CORE.some((p) => id.includes(p)) },
                        { name: 'vendor-editor', test: (id) => id.includes('@tiptap') || id.includes('/tiptap/') },
                        { name: 'vendor-charts', test: (id) => id.includes('@unovis') },
                        { name: 'vendor-flow', test: (id) => id.includes('@vue-flow') },
                    ],
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
            '/api': { target: 'http://localhost:8000', changeOrigin: false },
        },
    },
    // Every proxy keeps the browser's Host header (changeOrigin: false): the
    // backend picks the site by Host, and a rewritten `localhost:8000` sent
    // all sites of the bench to the active-site fallback.
    server: {
        port: 5173,
        host: true,
        allowedHosts: allowedHosts,
        // App files (dashboard widgets) live beside the framework, outside its root.
        fs: { allow: [appsDir] },
        hmr: {
            // When accessed through a reverse proxy / tunnel (e.g. dev2.itmlt.win),
            // tell the browser to connect HMR WebSocket on the standard HTTPS port
            // so the proxy doesn't need to expose port 5173 externally. No fixed
            // host: the client uses the page's own, so every site's domain works.
            path: 'vite-hmr',
            clientPort: 443,
            protocol: 'wss',
        },
        proxy: {
            // WebSocket endpoints — must be listed BEFORE the general /api rule
            '/api/v1/ws': {
                target: 'http://localhost:8000',
                ws: true,
            },
            // REST API, and WebSockets apps mount under their own routes
            // (e.g. /api/v1/app/lagoo/lagoo/ws)
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: false,
                ws: true,
            },
            // Static assets from app public/ directories
            '/assets': {
                target: 'http://localhost:8000',
                changeOrigin: false,
            },
            // Public www pages: proxy clean URLs (no file extension) to backend
            [CLEAN_URL_PROXY_REGEX]: {
                target: 'http://localhost:8000',
                changeOrigin: false,
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
