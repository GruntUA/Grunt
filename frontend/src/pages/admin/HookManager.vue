<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '@/core/api/client'
import {
    Zap,
    Code,
    Database,
    Search,
    CheckCircle2,
    AlertCircle,
    ExternalLink
} from '@lucide/vue'
import { Input } from '@/components/ui/input'


interface HookEntry {
    source: string
    event: string
    handler: string
    priority: number
    doctype: string
}

const hooks = ref<HookEntry[]>([])
const loading = ref(true)
const searchQuery = ref('')
const filterSource = ref('all')

async function fetchHooks() {
    loading.value = true
    try {
        const res = await api.get('/api/v1/hooks/')
        hooks.value = res.data.data
    } finally {
        loading.value = false
    }
}

const filteredHooks = computed(() => {
    return hooks.value.filter(h => {
        const matchesSearch =
            h.event.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
            h.handler.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
            h.doctype.toLowerCase().includes(searchQuery.value.toLowerCase())

        const matchesSource = filterSource.value === 'all' || h.source.toLowerCase().includes(filterSource.value.toLowerCase())

        return matchesSearch && matchesSource
    }).map(h => ({
        ...h,
        displaySource: h.source.includes('Python') ? 'Python' : 'Server Script',
        isPython: h.source.includes('Python'),
        icon: h.source.includes('Python') ? Code : Database
    })).sort((a, b) => a.doctype.localeCompare(b.doctype) || a.event.localeCompare(b.event))
})

onMounted(fetchHooks)
</script>

<template>
    <div class="flex flex-col h-full bg-background">
        <div class="px-8 py-6 border-b flex flex-col gap-6 bg-card/50">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div
                        class="size-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary shadow-sm">
                        <Zap class="size-6" />
                    </div>
                    <div>
                        <h1 class="text-2xl font-bold tracking-tight">Менеджер хуків</h1>
                        <p class="text-sm text-muted-foreground">Перегляд та управління подіями системи</p>
                    </div>
                </div>
                <button @click="fetchHooks"
                    class="px-4 py-2 bg-primary text-primary-foreground rounded-lg font-medium shadow-sm hover:translate-y-[-1px] active:translate-y-0 transition-all">
                    Оновити
                </button>
            </div>

            <div class="flex items-center gap-4">
                <div class="relative flex-1">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                    <Input v-model="searchQuery" placeholder="Пошук за подією, обробником або DocType..."
                        class="pl-10 h-11 bg-card shadow-inner border-border/60" />
                </div>
                <div class="flex gap-2 p-1 bg-muted rounded-lg shadow-inner">
                    <button v-for="s in ['all', 'Python', 'Database']" :key="s" @click="filterSource = s"
                        class="px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-md transition-all"
                        :class="filterSource === s ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'">
                        {{ s === 'all' ? 'Всі' : s === 'Python' ? 'Python' : 'Scripts' }}
                    </button>
                </div>
            </div>
        </div>

        <div class="flex-1 overflow-hidden p-8">
            <div class="bg-card border border-border/60 rounded-2xl shadow-xl overflow-hidden h-full flex flex-col">
                <div
                    class="grid grid-cols-12 gap-4 px-6 py-4 border-b bg-muted/30 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    <div class="col-span-2">Джерело</div>
                    <div class="col-span-2">DocType</div>
                    <div class="col-span-3">Подія</div>
                    <div class="col-span-4">Обробник / Скрипт</div>
                    <div class="col-span-1 text-right">Пріор.</div>
                </div>

                <ScrollPanel class="flex-1">
                    <div v-if="loading" class="flex flex-col items-center justify-center h-[400px] gap-4">
                        <div class="size-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
                        <span class="text-sm font-medium text-muted-foreground">Завантаження конфігурації...</span>
                    </div>

                    <div v-else-if="filteredHooks.length === 0"
                        class="flex flex-col items-center justify-center h-[400px] text-center">
                        <AlertCircle class="size-12 text-muted-foreground/20 mb-4" />
                        <h3 class="text-lg font-bold text-foreground/70">Хуків не знайдено</h3>
                        <p class="text-sm text-muted-foreground">Спробуйте змінити параметри пошуку</p>
                    </div>

                    <div v-else class="divide-y divide-border/40">
                        <div v-for="(h, i) in filteredHooks" :key="i"
                            class="grid grid-cols-12 gap-4 px-6 py-4 items-center hover:bg-muted/30 transition-colors group">
                            <div class="col-span-2 flex items-center gap-2">
                                <component :is="h.icon" class="size-3.5"
                                    :class="h.isPython ? 'text-primary' : 'text-amber-500'" />
                                <span class="text-xs font-semibold">{{ h.displaySource }}</span>
                            </div>
                            <div class="col-span-2">
                                <Badge severity="contrast" class="font-mono text-[10px] py-0 px-2 tracking-tighter"
                                    :class="h.doctype === '*' ? 'bg-muted text-muted-foreground' : 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'">
                                    {{ h.doctype }}</Badge>
                            </div>
                            <div class="col-span-3">
                                <span class="text-sm font-bold text-foreground/90">{{ h.event }}</span>
                            </div>
                            <div class="col-span-4 flex items-center justify-between pr-4">
                                <span class="text-sm text-muted-foreground font-mono truncate max-w-[280px]"
                                    :title="h.handler">{{ h.handler }}</span>
                                <a v-if="h.source.includes('Database')" :href="`/list/ServerScript/${h.handler}`"
                                    class="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 hover:bg-muted rounded text-primary">
                                    <ExternalLink class="size-4" />
                                </a>
                            </div>
                            <div class="col-span-1 text-right tabular-nums">
                                <span class="text-xs font-medium"
                                    :class="h.priority < 10 ? 'text-rose-500' : 'text-muted-foreground'">{{ h.priority
                                    }}</span>
                            </div>
                        </div>
                    </div>
                </ScrollPanel>

                <div
                    class="px-6 py-3 border-t bg-muted/10 flex items-center justify-between text-[11px] text-muted-foreground font-medium">
                    <div class="flex items-center gap-4">
                        <span class="flex items-center gap-1.5">
                            <CheckCircle2 class="size-3.5 text-emerald-500" /> Систему активовано
                        </span>
                        <span class="flex items-center gap-1.5">
                            <Zap class="size-3.5 text-primary" /> Останній запуск: щойно
                        </span>
                    </div>
                    <span>Всього хуків: {{ filteredHooks.length }}</span>
                </div>
            </div>
        </div>
    </div>
</template>
