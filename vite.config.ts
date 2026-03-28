import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
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
    plugins: [vue()],
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
