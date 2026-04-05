import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'
import fs from 'fs'

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
        VitePWA({
            registerType: 'prompt',         // expose updateSW() so we can show custom UI
            injectRegister: null,           // we register manually in main.ts
            devOptions: { enabled: false }, // off in dev — no stale assets
            manifest: false,               // manifest lives in public/manifest.webmanifest
            workbox: {
                // Precache all build assets (JS/CSS/fonts/icons)
                globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
                // Runtime: cache API metadata (DocType definitions) — stale-while-revalidate
                runtimeCaching: [
                    {
                        urlPattern: /\/api\/v1\/meta\/doctypes/,
                        handler: 'StaleWhileRevalidate',
                        options: {
                            cacheName: 'grunt-meta',
                            expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 },
                        },
                    },
                    // Cache Google Fonts
                    {
                        urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com/,
                        handler: 'CacheFirst',
                        options: {
                            cacheName: 'grunt-fonts',
                            expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
                        },
                    },
                ],
                // Don't intercept push-notification SW
                navigateFallback: '/index.html',
                navigateFallbackDenylist: [/^\/api/, /^\/sw\.js/],
            },
        }),
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './frontend/src'),
            ...appAliases,
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
