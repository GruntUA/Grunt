import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import fs from 'fs'
import Components from 'unplugin-vue-components/vite'

// shadcn-vue primitives — tag names auto-resolve to frontend/src/components/ui/*.
const SHADCN_UI_COMPONENTS: Record<string, string> = {
    Button: 'button',
    Input: 'input',
    Checkbox: 'checkbox',
    Switch: 'switch',
    Separator: 'separator',
    Badge: 'badge',
    Skeleton: 'skeleton',
    Avatar: 'avatar',
    AvatarImage: 'avatar',
    AvatarFallback: 'avatar',
    Spinner: 'spinner',
    Popover: 'popover',
    PopoverAnchor: 'popover',
    PopoverContent: 'popover',
    PopoverTrigger: 'popover',
    Dialog: 'dialog',
    DialogContent: 'dialog',
    DialogHeader: 'dialog',
    DialogTitle: 'dialog',
    DialogFooter: 'dialog',
    DialogClose: 'dialog',
    Progress: 'progress',
    Breadcrumb: 'breadcrumb',
    BreadcrumbList: 'breadcrumb',
    BreadcrumbItem: 'breadcrumb',
    BreadcrumbLink: 'breadcrumb',
    BreadcrumbPage: 'breadcrumb',
    BreadcrumbSeparator: 'breadcrumb',
    BreadcrumbEllipsis: 'breadcrumb',
    Sheet: 'sheet',
    SheetContent: 'sheet',
    SheetHeader: 'sheet',
    SheetTitle: 'sheet',
    SheetFooter: 'sheet',
    SheetClose: 'sheet',
    Select: 'select',
    SelectContent: 'select',
    SelectGroup: 'select',
    SelectItem: 'select',
    SelectLabel: 'select',
    SelectSeparator: 'select',
    SelectTrigger: 'select',
    SelectValue: 'select',
    Combobox: 'combobox',
    MultiSelect: 'multi-select',
    DropdownMenu: 'dropdown-menu',
    DropdownMenuTrigger: 'dropdown-menu',
    DropdownMenuContent: 'dropdown-menu',
    DropdownMenuItem: 'dropdown-menu',
    DropdownMenuSeparator: 'dropdown-menu',
    DropdownMenuLabel: 'dropdown-menu',
    DropdownMenuGroup: 'dropdown-menu',
    DropdownMenuRadioGroup: 'dropdown-menu',
    DropdownMenuRadioItem: 'dropdown-menu',
    DropdownMenuCheckboxItem: 'dropdown-menu',
    Tabs: 'tabs',
    TabsList: 'tabs',
    TabsTrigger: 'tabs',
    TabsContent: 'tabs',
    DatePicker: 'date-picker',
    TreeSelect: 'tree-select',
    Textarea: 'textarea',
    Table: 'table',
    TableHeader: 'table',
    TableBody: 'table',
    TableRow: 'table',
    TableHead: 'table',
    TableCell: 'table',
    Tooltip: 'tooltip',
    TooltipTrigger: 'tooltip',
    TooltipContent: 'tooltip',
}

function ShadcnUiResolver() {
    return (name: string) => {
        const dir = SHADCN_UI_COMPONENTS[name]
        if (dir) {
            return { name, from: `@/components/ui/${dir}` }
        }
    }
}

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
                ShadcnUiResolver(),
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
                    if (isVueVendorModule(id)) return 'vendor-vue'
                    if (id.includes('@tanstack/vue-query')) return 'vendor-query'
                    if (id.includes('/clsx/') || id.includes('tailwind-merge')) return 'vendor-ui'
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
