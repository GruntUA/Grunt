<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onUnmounted, defineComponent } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ListboxFilter, injectListboxRootContext } from 'reka-ui'
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
import { appUrl, docUrl } from '@/core/workspaceUrl'
import { Command, CommandList, CommandGroup, CommandItem, CommandShortcut } from '@/components/ui/command'
import { Kbd } from '@/components/ui/kbd'
import { Button } from '@/components/ui/button'
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

// Global shortcut: Mod+K
useShortcut('Mod+K', () => uiStore.toggleCommandPalette(), { preventDefault: true, allowInInput: true })

// Quick create: Alt+N (⌥N) - browsers reserve Ctrl+N and never deliver it
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

        // Inline calculator: "2+2*2" or "=2+2*2" -> "= 6" (select to copy).
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
                    run: () => navigateTo(appUrl({ type: 'Workspace', name: ws.name })),
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
                        navigateTo(docUrl(dt.name, null, ws?.name))
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

// Keyboard navigation is the Command (reka Listbox) itself. The search box is
// the bare ListboxFilter rather than <CommandInput>: CommandInput drives the
// Command's client-side text filter, which would hide server hits that don't
// contain the query (fuzzy/field matches, calculator results). Results arrive
// after typing, so the first one is re-highlighted whenever the list changes -
// Enter then opens it.
const flatList = computed<unknown[]>(() => {
    if (quickCreateOpen.value) return quickCreateDoctypes.value
    if (!search.value.trim()) return staticActions.value
    return results.value
})

const HighlightFirst = defineComponent({
    props: { items: { type: Array, required: true } },
    setup(props) {
        const listbox = injectListboxRootContext()
        watch(() => props.items, () => nextTick(() => listbox.highlightFirstItem()), { immediate: true })
        return () => null
    },
})
</script>

<template>
    <Dialog :open="uiStore.isCommandPaletteOpen" @update:open="(v) => { if (!v) uiStore.closeCommandPalette() }">
        <DialogContent class="max-w-xl overflow-hidden p-0" :show-close-button="false">
            <DialogTitle class="sr-only">{{ t('Search documents, apps or actions...') }}</DialogTitle>
            <DialogDescription class="sr-only">{{ t('Search documents, apps or actions...') }}</DialogDescription>

            <Command>
                <HighlightFirst :items="flatList" />
                <div data-slot="command-input-wrapper" class="flex h-11 items-center gap-2 border-b px-3">
                    <Search class="size-4 shrink-0 opacity-50" />
                    <ListboxFilter v-model="search" auto-focus
                        :placeholder="quickCreateOpen ? t('Select DocType to create a new record') : t('Search documents, apps or actions...')"
                        class="placeholder:text-muted-foreground flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-hidden" />
                    <Kbd>Esc</Kbd>
                </div>

                <CommandList class="max-h-[400px]">
                    <div v-if="loading && results.length === 0"
                        class="py-6 text-center text-sm text-muted-foreground">
                        {{ t('Searching...') }}
                    </div>

                    <CommandGroup v-if="quickCreateOpen" :heading="t('Quick create')">
                        <CommandItem v-for="dt in quickCreateDoctypes" :key="dt.name" :value="`qc-${dt.name}`" @select="createDoc(dt)">
                            <FilePlus />
                            <span>{{ dt.label || dt.name }}</span>
                        </CommandItem>
                    </CommandGroup>

                    <CommandGroup v-else-if="!search" :heading="t('Quick actions')">
                        <CommandItem v-for="action in staticActions" :key="action.id" :value="action.id" @select="action.run()">
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
                            <Kbd>↑↓</Kbd> {{ t('Navigate') }}
                        </span>
                        <span class="flex items-center gap-1">
                            <Kbd>↵</Kbd> {{ t('Select') }}
                        </span>
                    </div>
                    <Button v-if="search.trim().length >= 2" variant="link" size="xs" class="h-auto p-0 text-foreground"
                        @click="navigateTo(`/grunt/search?q=${encodeURIComponent(search)}`)">
                        {{ t('All results →') }}
                    </Button>
                    <Kbd v-else>Esc</Kbd>
                </div>
            </Command>
        </DialogContent>
    </Dialog>
</template>
