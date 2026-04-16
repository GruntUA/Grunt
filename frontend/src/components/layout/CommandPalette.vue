<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import { useWorkspaceStore } from '@/stores/workspace'
import { useUIStore } from '@/stores/ui'
import api from '@/core/api/client'
import {
    Dialog,
    DialogContent,
} from '@/components/ui/dialog'
import {
    Search,
    Command,
    CornerDownLeft,
    FileText,
    Plus,
    Settings,
    LogOut,
    LayoutGrid,
    FilePlus,
    Zap,
    Activity,
} from '@lucide/vue'
import { onKeyStroke } from '@vueuse/core'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const dtStore = useDocTypeStore()
const wsStore = useWorkspaceStore()
const uiStore = useUIStore()

const search = ref('')
const results = ref<any[]>([])
const loading = ref(false)
const selectedIndex = ref(0)
const quickCreateOpen = ref(false)
const quickCreateDoctype = ref('')

// Global shortcut: Ctrl+K or Cmd+K
onKeyStroke(['k', 'K'], (e) => {
    if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        uiStore.toggleCommandPalette()
    }
})

// Quick create: Ctrl+N or Cmd+N
onKeyStroke(['n', 'N'], (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey) {
        const active = document.activeElement
        if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || (active instanceof HTMLElement && active.isContentEditable)) {
            return
        }
        e.preventDefault()
        quickCreateOpen.value = true
        uiStore.openCommandPalette()
    }
})

// Listen for custom trigger event (e.g. from Sidebar)
const handleToggleSearch = () => uiStore.toggleCommandPalette()

onMounted(() => {
    window.addEventListener('toggle-search', handleToggleSearch)
})

onUnmounted(() => {
    window.removeEventListener('toggle-search', handleToggleSearch)
})

// Auto-focus and reset on open
watch(() => uiStore.isCommandPaletteOpen, (open) => {
    if (open) {
        search.value = ''
        results.value = []
        selectedIndex.value = 0
        quickCreateOpen.value = false
        quickCreateDoctype.value = ''
    }
})

onMounted(() => {
    const onOpenQuickCreate = () => {
        uiStore.openCommandPalette()
        quickCreateOpen.value = true
        quickCreateDoctype.value = ''
    }
    window.addEventListener('command-palette-open-quick-create', onOpenQuickCreate)
    onUnmounted(() => {
        window.removeEventListener('command-palette-open-quick-create', onOpenQuickCreate)
    })
})

async function handleLogout() {
    uiStore.closeCommandPalette()
    await auth.logout()
    router.push('/login')
}

// Static actions
const staticActions = computed(() => [
    { id: 'quick-create', title: t('Quick create (Ctrl+N)'), icon: FilePlus, action: () => { quickCreateOpen.value = true; uiStore.openCommandPalette() }, category: t('Actions') },
    { id: 'new-doctype', title: t('Create new DocType'), icon: Plus, action: () => navigateTo('/grunt/list/DocType/new'), category: t('Actions') },
    { id: 'view-hooks', title: t('View hooks'), icon: Zap, action: () => navigateTo('/grunt/hooks'), category: t('Settings') },
    { id: 'activity-log', title: t('Activity log'), icon: Activity, action: () => navigateTo('/grunt/activity-log'), category: t('Settings') },
    { id: 'settings', title: t('System settings'), icon: Settings, action: () => navigateTo('/grunt/list/SystemSettings/SystemSettings'), category: t('Actions') },
    { id: 'logout', title: t('Log out'), icon: LogOut, action: handleLogout, category: t('Actions') },
])

// Search logic
watch(search, async (val) => {
    const q = val.trim().toLowerCase()
    if (!q) {
        results.value = []
        return
    }

    loading.value = true
    try {
        const matchedResults: any[] = []

        // 1. Match Static Actions
        staticActions.value.forEach(a => {
            if (a.title.toLowerCase().includes(q)) matchedResults.push({ ...a, type: 'action' })
        })

        // 2. Match Workspaces (load on demand)
        if (wsStore.workspaces.length === 0) await wsStore.loadAll()
        wsStore.workspaces.forEach(ws => {
            if (ws.label.toLowerCase().includes(q) || ws.name.toLowerCase().includes(q)) {
                matchedResults.push({
                    id: `ws-${ws.name}`,
                    title: ws.label,
                    type: 'workspace',
                    icon: LayoutGrid,
                    action: () => navigateTo(`/${ws.name}`),
                    category: t('Apps')
                })
            }
        })

        // 3. Match DocTypes
        if (dtStore.doctypes.length === 0) await dtStore.loadAll()
        dtStore.doctypes.forEach((dt: any) => {
            if (dt.label.toLowerCase().includes(q) || dt.name.toLowerCase().includes(q)) {
                matchedResults.push({
                    id: `dt-${dt.name}`,
                    title: dt.label,
                    subtitle: t('Go to list {label}', { label: dt.label }),
                    type: 'doctype',
                    icon: FilePlus,
                    action: () => {
                        const ws = wsStore.workspaces.find(w => w.items.some(i => i.link_to === dt.name))
                        if (dt.is_singleton) {
                            navigateTo(`/${ws?.name || 'grunt'}/list/${dt.name}/${dt.name}`)
                        } else {
                            navigateTo(`/${ws?.name || 'grunt'}/list/${dt.name}`)
                        }
                    },
                    category: t('DocTypes')
                })
            }
        })

        // 4. Remote search for documents
        if (q.length >= 2) {
            const res = await api.get(`/api/v1/search?q=${encodeURIComponent(q)}`)
            const docs = (res.data || []).map((d: any) => ({
                ...d,
                id: `doc-${d.doctype}-${d.id || d.name}`,
                type: 'document',
                icon: FileText,
                action: () => {
                    const ws = wsStore.workspaces.find(w => w.items.some(i => i.link_to === d.doctype))
                    navigateTo(`/${ws?.name || 'grunt'}/list/${d.doctype}/${d.id || d.name}`)
                },
                category: t('Documents')
            }))
            matchedResults.push(...docs)
        }

        results.value = matchedResults
        selectedIndex.value = 0
    } catch (err) {
        console.error('Search error:', err)
    } finally {
        loading.value = false
    }
})

function navigateTo(path: string) {
    uiStore.closeCommandPalette()
    router.push(path)
}

function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
        e.preventDefault()
        selectedIndex.value = (selectedIndex.value + 1) % results.value.length
    } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        selectedIndex.value = (selectedIndex.value - 1 + results.value.length) % results.value.length
    } else if (e.key === 'Enter' && results.value[selectedIndex.value]) {
        e.preventDefault()
        results.value[selectedIndex.value].action()
    }
}

// Grouped results for the UI
const groupedResults = computed(() => {
    const groups: Record<string, any[]> = {}
    results.value.forEach(r => {
        const cat = r.category || t('Other')
        if (!groups[cat]) groups[cat] = []
        groups[cat].push(r)
    })
    return groups
})

const flatResults = computed(() => results.value)

</script>

<template>
    <Dialog :open="uiStore.isCommandPaletteOpen" @update:open="uiStore.closeCommandPalette">
        <DialogContent class="p-0 overflow-hidden max-w-2xl border-none shadow-2xl bg-card">
            <div class="relative flex items-center border-b px-4 py-4">
                <Search class="mr-3 h-5 w-5 shrink-0 opacity-50 text-primary" />
                <input v-model="search" :placeholder="t('Search documents, apps or actions...')"
                    class="flex h-10 w-full rounded-md bg-transparent py-3 text-base outline-none placeholder:text-muted-foreground"
                    @keydown="onKeyDown" autofocus />
                <div class="flex items-center gap-1.5 ml-2">
                    <kbd
                        class="px-2 py-1 rounded bg-muted border text-[10px] font-bold text-muted-foreground shadow-sm">ESC</kbd>
                </div>
            </div>

            <div class="max-h-[450px] overflow-y-auto p-2 scrollbar-thin">
                <div v-if="loading && results.length === 0"
                    class="py-12 text-center text-sm text-muted-foreground flex flex-col items-center gap-3">
                    <div class="size-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
                    {{ t('Searching...') }}
                </div>

                <div v-else-if="search.length > 0 && results.length === 0 && !loading"
                    class="py-12 text-center text-sm text-muted-foreground italic">
                    {{ t('Nothing found for') }} "{{ search }}"
                </div>

                <div v-if="quickCreateOpen" class="px-4 py-4 border-b">
                    <div class="flex items-center justify-between mb-2">
                        <div>
                            <p class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Quick Create</p>
                            <p class="text-xs text-muted-foreground">{{ t('Select DocType to create a new record') }}
                            </p>
                        </div>
                        <button class="text-muted-foreground hover:text-foreground"
                            @click="quickCreateOpen = false">Esc</button>
                    </div>
                    <div class="flex gap-2">
                        <select v-model="quickCreateDoctype" class="flex-1 p-2 border rounded bg-background">
                            <option value="" disabled>Оберіть DocType...</option>
                            <option v-for="dt in dtStore.doctypes" :key="dt.name" :value="dt.name">{{ dt.label ||
                                dt.name }}</option>
                        </select>
                        <button class="px-3 py-2 rounded bg-primary text-primary-foreground"
                            :disabled="!quickCreateDoctype"
                            @click="{ const ws = wsStore.active?.name || 'grunt'; uiStore.closeCommandPalette(); quickCreateOpen = false; router.push(`/${ws}/list/${quickCreateDoctype}/new`) }">
                            {{ t('Create') }}
                        </button>
                    </div>
                </div>

                <div v-else-if="search.length === 0" class="py-6 px-4">
                    <p class="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-4">{{ t('Quick actions') }}</p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <button v-for="action in staticActions" :key="action.id"
                            class="flex items-center gap-3 p-3 rounded-xl border bg-muted/30 hover:bg-primary/5 hover:border-primary/30 transition-all text-left group"
                            @click="action.action">
                            <div
                                class="size-9 rounded-lg bg-background border flex items-center justify-center text-muted-foreground group-hover:text-primary transition-colors shadow-sm">
                                <component :is="action.icon" class="size-5" />
                            </div>
                            <span class="text-sm font-medium">{{ action.title }}</span>
                        </button>
                    </div>
                </div>

                <template v-else>
                    <div v-for="(items, category) in groupedResults" :key="category" class="mb-4 last:mb-2">
                        <p
                            class="px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest opacity-60">
                            {{ category }}
                        </p>
                        <div class="space-y-0.5">
                            <button v-for="item in items" :key="item.id"
                                class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-200 group relative"
                                :class="flatResults[selectedIndex]?.id === item.id ? 'bg-primary text-primary-foreground shadow-md -translate-y-0.5' : 'hover:bg-accent/50 text-foreground'"
                                @click="item.action"
                                @mouseenter="selectedIndex = flatResults.findIndex(r => r.id === item.id)">

                                <div class="size-8 rounded-lg border flex items-center justify-center shrink-0 shadow-sm"
                                    :class="flatResults[selectedIndex]?.id === item.id ? 'bg-white/20 border-white/20' : 'bg-background border-border/50'">
                                    <component :is="item.icon" class="size-4" />
                                </div>

                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center gap-2">
                                        <span class="font-semibold text-sm truncate">{{ item.title }}</span>
                                        <span v-if="item.doctype"
                                            class="text-[10px] px-1.5 py-0.5 rounded-full font-bold uppercase opacity-70"
                                            :class="flatResults[selectedIndex]?.id === item.id ? 'bg-white/20 text-white' : 'bg-muted text-muted-foreground'">
                                            {{ item.doctype_label || item.doctype }}
                                        </span>
                                    </div>
                                    <p v-if="item.subtitle" class="text-[11px] truncate opacity-80"
                                        :class="flatResults[selectedIndex]?.id === item.id ? 'text-white/80' : 'text-muted-foreground'">
                                        {{ item.subtitle }}
                                    </p>
                                </div>

                                <div v-if="flatResults[selectedIndex]?.id === item.id"
                                    class="shrink-0 flex items-center gap-1 text-[10px] font-bold opacity-80">
                                    <span>ENTER</span>
                                    <CornerDownLeft class="size-3" />
                                </div>
                            </button>
                        </div>
                    </div>
                </template>
            </div>

            <div
                class="flex items-center justify-between px-4 py-3 bg-muted/40 border-t text-[10px] text-muted-foreground font-medium">
                <div class="flex items-center gap-4">
                    <span class="flex items-center gap-1.5"><kbd
                            class="border rounded px-1.5 py-0.5 bg-background shadow-sm text-foreground">↑↓</kbd>
                        Навігація</span>
                    <span class="flex items-center gap-1.5"><kbd
                            class="border rounded px-1.5 py-0.5 bg-background shadow-sm text-foreground">↵</kbd>
                        Вибрати</span>
                </div>
                <template v-if="search.length >= 2">
                    <button class="text-[10px] text-primary hover:underline font-semibold"
                        @click="navigateTo(`/grunt/search?q=${encodeURIComponent(search)}`)">
                        Всі результати →
                    </button>
                </template>
                <div v-else class="flex items-center gap-1.5 opacity-60">
                    <Command class="size-3" />
                    <span class="font-bold">K</span>
                </div>
            </div>
        </DialogContent>
    </Dialog>
</template>

<style scoped>
.scrollbar-thin::-webkit-scrollbar {
    width: 4px;
}

.scrollbar-thin::-webkit-scrollbar-track {
    background: transparent;
}

.scrollbar-thin::-webkit-scrollbar-thumb {
    background: hsl(var(--border));
    border-radius: 20px;
}
</style>
