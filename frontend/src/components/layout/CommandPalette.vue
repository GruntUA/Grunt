<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import { useAppStore } from '@/stores/app'
import { useUIStore } from '@/stores/ui'
import api from '@/core/api/client'
import {
    Search,
    FileText,
    Plus,
    Settings,
    LogOut,
    LayoutGrid,
    FilePlus,
    Zap,
    Activity,
    Equal,
} from '@lucide/vue'
import { useShortcut } from '@/core/composables/useShortcuts'
import { useToast } from '@/core/composables/useToast'
import { tryCalc, formatCalcResult } from '@/lib/calc'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { docUrl, workspaceUrl } from '@/core/workspaceUrl'
import { Command, CommandList, CommandGroup, CommandItem, CommandShortcut } from '@/components/ui/command'
import { Kbd } from '@/components/ui/kbd'
import { formatShortcut } from '@/core/shortcuts'

const { t } = useI18n()
const toast = useToast()
const router = useRouter()
const auth = useAuthStore()
const dtStore = useDocTypeStore()
const appStore = useAppStore()
const uiStore = useUIStore()

const search = ref('')
const results = ref<any[]>([])
const loading = ref(false)
const quickCreateOpen = ref(false)
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<any>(null)

// Global shortcut: Mod+K
useShortcut('Mod+K', () => uiStore.toggleCommandPalette(), { preventDefault: true, allowInInput: true })

// Quick create: Alt+N (⌥N) — browsers reserve Ctrl+N and never deliver it
useShortcut('Alt+N', () => openQuickCreate(), { preventDefault: true })

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
        activeIndex.value = 0
        nextTick(() => inputRef.value?.focus())
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
    { id: 'act-quick-create', title: t('Quick create'), shortcut: 'Alt+N', icon: FilePlus, run: openQuickCreate, category: t('Actions') },
    { id: 'act-new-doctype', title: t('Create new DocType'), icon: Plus, run: () => navigateTo('/grunt/DocType/new'), category: t('Actions') },
    { id: 'act-view-hooks', title: t('View hooks'), icon: Zap, run: () => navigateTo('/grunt/Hook'), category: t('Settings') },
    { id: 'act-activity-log', title: t('Activity log'), icon: Activity, run: () => navigateTo('/grunt/ActivityLog'), category: t('Settings') },
    { id: 'act-settings', title: t('System settings'), icon: Settings, run: () => navigateTo('/grunt/SystemSettings/SystemSettings'), category: t('Actions') },
    { id: 'act-logout', title: t('Log out'), icon: LogOut, run: handleLogout, category: t('Actions') },
])

// DocType list for quick-create mode.
const quickCreateDoctypes = computed(() => {
    const q = search.value.trim().toLowerCase()
    const all = [...dtStore.doctypes].sort((a: any, b: any) => (a.label || a.name).localeCompare(b.label || b.name))
    if (!q) return all
    return all.filter((dt: any) => (dt.label || '').toLowerCase().includes(q) || dt.name.toLowerCase().includes(q))
})

function createDoc(dt: any) {
    const ws = appStore.workspaces.find(w => w.items.some((i: any) => i.link_to === dt.name))
    navigateTo(docUrl(dt.name, 'new', ws?.name || appStore.active?.name))
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

        // Inline calculator: "2+2*2" or "=2+2*2" → "= 6" (select to copy).
        const calcExpr = val.trim().replace(/^=\s*/, '')
        const calc = tryCalc(calcExpr)
        if (calc !== null) {
            const answer = formatCalcResult(calc)
            matched.push({
                id: 'calc-result',
                title: `${calcExpr} = ${answer}`,
                subtitle: t('Copy result'),
                icon: Equal,
                category: t('Calculator'),
                run: () => {
                    void navigator.clipboard?.writeText(answer).catch(() => {})
                    toast.success(`${calcExpr} = ${answer}`, t('Copied'))
                    uiStore.closeCommandPalette()
                },
            })
        }

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
                    run: () => navigateTo(workspaceUrl(ws.name)),
                })
            }
        })

        if (dtStore.doctypes.length === 0) await dtStore.loadAll()
        dtStore.doctypes.forEach((dt: any) => {
            if (dt.label.toLowerCase().includes(q) || dt.name.toLowerCase().includes(q)) {
                matched.push({
                    id: `dt-${dt.name}`,
                    title: dt.label,
                    subtitle: t('Go to list {label}', { label: dt.label }),
                    icon: FilePlus,
                    category: t('DocTypes'),
                    run: () => {
                        const ws = appStore.workspaces.find(w => w.items.some((i: any) => i.link_to === dt.name))
                        navigateTo(dt.is_singleton
                            ? docUrl(dt.name, dt.name, ws?.name)
                            : docUrl(dt.name, null, ws?.name))
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
                        navigateTo(docUrl(d.doctype, docId, ws?.name))
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

// ── Manual keyboard highlight ────────────────────────────────────────────────
// shadcn's <Command> filters its own *static* children; this palette builds
// results asynchronously, so its built-in filter is bypassed entirely
// (no <CommandInput> → filterState.search stays empty → every item renders)
// and we drive arrow-key navigation ourselves over the flat result list.
const flatList = computed<any[]>(() => {
    if (quickCreateOpen.value) {
        return quickCreateDoctypes.value.map((dt: any) => ({ id: `qc-${dt.name}`, run: () => createDoc(dt) }))
    }
    if (!search.value.trim()) return staticActions.value
    return results.value
})

const activeId = computed(() => flatList.value[activeIndex.value]?.id)

watch([search, results, quickCreateOpen], () => { activeIndex.value = 0 })

function scrollActiveIntoView() {
    nextTick(() => {
        listRef.value?.$el?.querySelector?.('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
    })
}

function moveActive(delta: number) {
    const n = flatList.value.length
    if (!n) return
    activeIndex.value = (activeIndex.value + delta + n) % n
    scrollActiveIntoView()
}

function setActive(id: string) {
    const i = flatList.value.findIndex(x => x.id === id)
    if (i >= 0) activeIndex.value = i
}

function onInputKeydown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
        e.preventDefault()
        moveActive(1)
    } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        moveActive(-1)
    } else if (e.key === 'Enter') {
        e.preventDefault()
        flatList.value[activeIndex.value]?.run?.()
    }
}
</script>

<template>
    <Dialog :open="uiStore.isCommandPaletteOpen" @update:open="(v) => { if (!v) uiStore.closeCommandPalette() }">
        <DialogContent class="max-w-xl overflow-hidden p-0" :show-close-button="false">
            <DialogTitle class="sr-only">{{ t('Search documents, apps or actions...') }}</DialogTitle>
            <DialogDescription class="sr-only">{{ t('Search documents, apps or actions...') }}</DialogDescription>

            <Command :highlight-on-hover="false">
                <div class="flex h-11 items-center gap-2 border-b px-3">
                    <Search class="size-4 shrink-0 opacity-50" />
                    <input ref="inputRef" v-model="search"
                        :placeholder="quickCreateOpen ? t('Select DocType to create a new record') : t('Search documents, apps or actions...')"
                        class="placeholder:text-muted-foreground flex h-10 w-full bg-transparent py-3 text-sm outline-none"
                        @keydown="onInputKeydown" />
                    <Kbd>Esc</Kbd>
                </div>

                <CommandList ref="listRef" class="max-h-[400px]">
                    <div v-if="loading && results.length === 0"
                        class="py-6 text-center text-sm text-muted-foreground">
                        {{ t('Searching...') }}
                    </div>

                    <CommandGroup v-if="quickCreateOpen" :heading="t('Quick create')">
                        <CommandItem v-for="dt in quickCreateDoctypes" :key="dt.name" :value="`qc-${dt.name}`"
                            :data-active="activeId === `qc-${dt.name}` ? 'true' : undefined"
                            :class="activeId === `qc-${dt.name}` && 'bg-accent text-accent-foreground'"
                            @mouseenter="setActive(`qc-${dt.name}`)" @select="createDoc(dt)">
                            <FilePlus />
                            <span>{{ dt.label || dt.name }}</span>
                        </CommandItem>
                    </CommandGroup>

                    <CommandGroup v-else-if="!search" :heading="t('Quick actions')">
                        <CommandItem v-for="action in staticActions" :key="action.id" :value="action.id"
                            :data-active="activeId === action.id ? 'true' : undefined"
                            :class="activeId === action.id && 'bg-accent text-accent-foreground'"
                            @mouseenter="setActive(action.id)" @select="action.run()">
                            <component :is="action.icon" />
                            <span>{{ action.title }}</span>
                            <CommandShortcut v-if="action.shortcut">{{ formatShortcut(action.shortcut) }}</CommandShortcut>
                        </CommandItem>
                    </CommandGroup>

                    <template v-else>
                        <div v-if="!loading && results.length === 0"
                            class="py-6 text-center text-sm text-muted-foreground">
                            {{ t('Nothing found for') }} "{{ search }}"
                        </div>
                        <CommandGroup v-for="(items, category) in groupedResults" :key="category" :heading="category">
                            <CommandItem v-for="item in items" :key="item.id" :value="item.id"
                                :data-active="activeId === item.id ? 'true' : undefined"
                                :class="activeId === item.id && 'bg-accent text-accent-foreground'"
                                @mouseenter="setActive(item.id)" @select="item.run()">
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
                            <Kbd>↑↓</Kbd> {{ t('Navigate') }}
                        </span>
                        <span class="flex items-center gap-1">
                            <Kbd>↵</Kbd> {{ t('Select') }}
                        </span>
                    </div>
                    <button v-if="search.trim().length >= 2" class="font-medium text-foreground hover:underline"
                        @click="navigateTo(`/grunt/search?q=${encodeURIComponent(search)}`)">
                        {{ t('All results →') }}
                    </button>
                    <Kbd v-else>Esc</Kbd>
                </div>
            </Command>
        </DialogContent>
    </Dialog>
</template>
