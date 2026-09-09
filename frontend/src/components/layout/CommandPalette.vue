<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import { useAppStore } from '@/stores/app'
import { useUIStore } from '@/stores/ui'
import api from '@/core/api/client'
import {
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
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import {
    Command,
    CommandInput,
    CommandList,
    CommandGroup,
    CommandItem,
    CommandEmpty,
} from '@/components/ui/command'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const dtStore = useDocTypeStore()
const appStore = useAppStore()
const uiStore = useUIStore()

const search = ref('')
const results = ref<any[]>([])
const loading = ref(false)
const quickCreateOpen = ref(false)

// Global shortcut: Ctrl/Cmd+K
onKeyStroke(['k', 'K'], (e) => {
    if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        uiStore.toggleCommandPalette()
    }
})

// Quick create: Ctrl/Cmd+N
onKeyStroke(['n', 'N'], (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey) {
        const active = document.activeElement
        if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || (active instanceof HTMLElement && active.isContentEditable)) {
            return
        }
        e.preventDefault()
        openQuickCreate()
    }
})

const handleToggleSearch = () => uiStore.toggleCommandPalette()
const handleOpenQuickCreate = () => openQuickCreate()

onMounted(() => {
    window.addEventListener('toggle-search', handleToggleSearch)
    window.addEventListener('command-palette-open-quick-create', handleOpenQuickCreate)
})

onUnmounted(() => {
    window.removeEventListener('toggle-search', handleToggleSearch)
    window.removeEventListener('command-palette-open-quick-create', handleOpenQuickCreate)
})

function openQuickCreate() {
    uiStore.openCommandPalette()
    quickCreateOpen.value = true
    if (dtStore.doctypes.length === 0) dtStore.loadAll()
}

// Reset transient state when the palette opens; drop quick-create mode on close.
watch(() => uiStore.isCommandPaletteOpen, (open) => {
    if (open) {
        search.value = ''
        results.value = []
    } else {
        quickCreateOpen.value = false
    }
})

async function handleLogout() {
    uiStore.closeCommandPalette()
    await auth.logout()
    router.push('/login')
}

function navigateTo(path: string) {
    uiStore.closeCommandPalette()
    router.push(path)
}

const staticActions = computed(() => [
    { id: 'act-quick-create', title: t('Quick create (Ctrl+N)'), icon: FilePlus, run: openQuickCreate, category: t('Actions') },
    { id: 'act-new-doctype', title: t('Create new DocType'), icon: Plus, run: () => navigateTo('/grunt/DocType/new'), category: t('Actions') },
    { id: 'act-view-hooks', title: t('View hooks'), icon: Zap, run: () => navigateTo('/grunt/Hook'), category: t('Settings') },
    { id: 'act-activity-log', title: t('Activity log'), icon: Activity, run: () => navigateTo('/grunt/ActivityLog'), category: t('Settings') },
    { id: 'act-settings', title: t('System settings'), icon: Settings, run: () => navigateTo('/grunt/SystemSettings/SystemSettings'), category: t('Actions') },
    { id: 'act-logout', title: t('Log out'), icon: LogOut, run: handleLogout, category: t('Actions') },
])

// DocType list for quick-create mode — filtered client-side by CommandInput.
const quickCreateDoctypes = computed(() =>
    [...dtStore.doctypes].sort((a: any, b: any) => (a.label || a.name).localeCompare(b.label || b.name))
)

function createDoc(dt: any) {
    const ws = appStore.workspaces.find(w => w.items.some((i: any) => i.link_to === dt.name))
    navigateTo(`/${ws?.name || appStore.active?.name || 'grunt'}/${dt.name}/new`)
}

// Async search across actions, workspaces, doctypes and indexed documents.
watch(search, async (val) => {
    const q = val.trim().toLowerCase()
    if (!q) {
        results.value = []
        return
    }

    loading.value = true
    try {
        const matched: any[] = []

        staticActions.value.forEach(a => {
            if (a.title.toLowerCase().includes(q)) matched.push(a)
        })

        if (appStore.workspaces.length === 0) await appStore.loadAll()
        appStore.workspaces.forEach(ws => {
            if (ws.label.toLowerCase().includes(q) || ws.name.toLowerCase().includes(q)) {
                matched.push({
                    id: `ws-${ws.name}`,
                    title: ws.label,
                    icon: LayoutGrid,
                    category: t('Apps'),
                    run: () => navigateTo(`/${ws.name}`),
                })
            }
        })

        if (dtStore.doctypes.length === 0) await dtStore.loadAll()
        dtStore.doctypes.forEach((dt: any) => {
            if (dt.label.toLowerCase().includes(q) || dt.name.toLowerCase().includes(q)) {
                matched.push({
                    id: `dt-${dt.name}`,
                    title: dt.label,
                    subtitle: t('Go to list {label}').replace('{label}', dt.label),
                    icon: FilePlus,
                    category: t('DocTypes'),
                    run: () => {
                        const ws = appStore.workspaces.find(w => w.items.some((i: any) => i.link_to === dt.name))
                        navigateTo(dt.is_singleton
                            ? `/${ws?.name || 'grunt'}/${dt.name}/${dt.name}`
                            : `/${ws?.name || 'grunt'}/${dt.name}`)
                    },
                })
            }
        })

        if (q.length >= 2) {
            const res = await api.get(`/api/v1/method/grunt.api.v1.search.global_search?q=${encodeURIComponent(q)}`)
            ;(res.data?.data || []).forEach((d: any) => {
                const docId = d.id || d.name
                matched.push({
                    id: `doc-${d.doctype}-${docId}`,
                    title: d.display_title || d.title || docId,
                    subtitle: d.doctype_label || d.doctype,
                    icon: FileText,
                    category: t('Documents'),
                    run: () => {
                        const ws = appStore.workspaces.find(w => w.items.some((i: any) => i.link_to === d.doctype))
                        navigateTo(`/${ws?.name || 'grunt'}/${d.doctype}/${docId}`)
                    },
                })
            })
        }

        results.value = matched
    } catch (err) {
        console.error('Search error:', err)
    } finally {
        loading.value = false
    }
})

const groupedResults = computed(() => {
    const groups: Record<string, any[]> = {}
    results.value.forEach(r => {
        const cat = r.category || t('Other')
        ;(groups[cat] ||= []).push(r)
    })
    return groups
})
</script>

<template>
    <Dialog :open="uiStore.isCommandPaletteOpen" @update:open="(v) => { if (!v) uiStore.closeCommandPalette() }">
        <DialogContent class="max-w-xl overflow-hidden p-0" :show-close-button="false">
            <DialogTitle class="sr-only">{{ t('Search documents, apps or actions...') }}</DialogTitle>
            <DialogDescription class="sr-only">{{ t('Search documents, apps or actions...') }}</DialogDescription>

            <Command>
                <CommandInput
                    :placeholder="quickCreateOpen ? t('Select DocType to create a new record') : t('Search documents, apps or actions...')"
                    @update:model-value="(v: unknown) => (search = String(v ?? ''))" />

                <CommandList class="max-h-[400px]">
                    <div v-if="loading && results.length === 0"
                        class="py-6 text-center text-sm text-muted-foreground">
                        {{ t('Searching...') }}
                    </div>

                    <CommandGroup v-if="quickCreateOpen" :heading="t('Quick create')">
                        <CommandItem v-for="dt in quickCreateDoctypes" :key="dt.name" :value="`qc-${dt.name}`"
                            @select="createDoc(dt)">
                            <FilePlus />
                            <span>{{ dt.label || dt.name }}</span>
                        </CommandItem>
                    </CommandGroup>

                    <CommandGroup v-else-if="!search" :heading="t('Quick actions')">
                        <CommandItem v-for="action in staticActions" :key="action.id" :value="action.id"
                            @select="action.run()">
                            <component :is="action.icon" />
                            <span>{{ action.title }}</span>
                        </CommandItem>
                    </CommandGroup>

                    <template v-else>
                        <CommandEmpty v-if="!loading">{{ t('Nothing found for') }} "{{ search }}"</CommandEmpty>
                        <CommandGroup v-for="(items, category) in groupedResults" :key="category" :heading="category">
                            <CommandItem v-for="item in items" :key="item.id" :value="item.id" @select="item.run()">
                                <component :is="item.icon" />
                                <span class="flex-1 truncate">{{ item.title }}</span>
                                <span v-if="item.subtitle" class="truncate text-xs text-muted-foreground">
                                    {{ item.subtitle }}
                                </span>
                            </CommandItem>
                        </CommandGroup>
                    </template>
                </CommandList>

                <div class="flex items-center justify-between gap-4 border-t px-3 py-2 text-xs text-muted-foreground">
                    <div class="flex items-center gap-3">
                        <span class="flex items-center gap-1">
                            <kbd class="rounded border bg-muted px-1 font-sans">↑↓</kbd> Навігація
                        </span>
                        <span class="flex items-center gap-1">
                            <kbd class="rounded border bg-muted px-1 font-sans">↵</kbd> Вибрати
                        </span>
                    </div>
                    <button v-if="search.trim().length >= 2" class="font-medium text-foreground hover:underline"
                        @click="navigateTo(`/grunt/search?q=${encodeURIComponent(search)}`)">
                        Всі результати →
                    </button>
                    <kbd v-else class="rounded border bg-muted px-1 font-sans">Esc</kbd>
                </div>
            </Command>
        </DialogContent>
    </Dialog>
</template>
