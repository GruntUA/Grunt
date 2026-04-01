<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/core/api/client'
import {
    Dialog,
    DialogContent,
} from '@/components/ui/dialog'
import { Search, Command, CornerDownLeft, FileText, ChevronRight } from 'lucide-vue-next'
import { useMagicKeys } from '@vueuse/core'

const open = ref(false)
const search = ref('')
const results = ref<any[]>([])
const loading = ref(false)
const selectedIndex = ref(0)
const router = useRouter()

const { Meta_K, Ctrl_K } = useMagicKeys()

watch([Meta_K, Ctrl_K], (v) => {
    if (v[0] || v[1]) {
        open.value = !open.value
    }
})

function toggleOpen() {
    open.value = !open.value
}

onMounted(() => {
    window.addEventListener('toggle-search', toggleOpen)
})

onUnmounted(() => {
    window.removeEventListener('toggle-search', toggleOpen)
})

watch(search, async (val) => {
    if (val.length < 2) {
        results.value = []
        return
    }

    loading.value = true
    try {
        const res = await api.get(`/api/v1/search?q=${encodeURIComponent(val)}`)
        results.value = res.data
        selectedIndex.value = 0
    } finally {
        loading.value = false
    }
})

function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
        e.preventDefault()
        selectedIndex.value = (selectedIndex.value + 1) % results.value.length
    } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        selectedIndex.value = (selectedIndex.value - 1 + results.value.length) % results.value.length
    } else if (e.key === 'Enter' && results.value[selectedIndex.value]) {
        e.preventDefault()
        selectResult(results.value[selectedIndex.value])
    }
}

function selectResult(result: any) {
    open.value = false
    search.value = ''
    results.value = []

    // Determine route based on result type
    // In Grunt, doc routes are typically /:workspace/list/:doctype/:id
    // But we need the workspace name. We can get it from the current route or store.
    const workspaceName = router.currentRoute.value.params.workspaceName || 'grunt'
    router.push(`/${workspaceName}/list/${result.doctype}/${result.id || result.name}`)
}

defineExpose({ open })
</script>

<template>
    <Dialog v-model:open="open">
        <DialogContent class="p-0 overflow-hidden max-w-2xl border-none shadow-2xl">
            <div class="relative flex items-center border-b px-4 py-3 bg-muted/20">
                <Search class="mr-2 h-4 w-4 shrink-0 opacity-50" />
                <input v-model="search" placeholder="Пункт меню або документ..."
                    class="flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                    @keydown="onKeyDown" autofocus />
                <div
                    class="flex items-center gap-1 border rounded px-1.5 py-0.5 bg-background text-[10px] font-medium text-muted-foreground ml-2">
                    <span class="text-xs">ESC</span>
                </div>
            </div>

            <div class="max-h-[400px] overflow-y-auto p-2 space-y-1">
                <div v-if="loading && results.length === 0" class="py-12 text-center text-sm text-muted-foreground">
                    Шукаємо...
                </div>

                <div v-else-if="search.length >= 2 && results.length === 0 && !loading"
                    class="py-12 text-center text-sm text-muted-foreground">
                    Нічого не знайдено для "{{ search }}"
                </div>

                <div v-else-if="search.length < 2 && results.length === 0"
                    class="py-12 text-center text-sm text-muted-foreground">
                    Введіть мінімум 2 символи для пошуку...
                </div>

                <template v-else>
                    <button v-for="(result, index) in results" :key="result.doctype + result.id"
                        class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-200 group"
                        :class="selectedIndex === index ? 'bg-primary/10 text-primary shadow-sm' : 'hover:bg-accent/50 text-foreground/80'"
                        @click="selectResult(result)" @mouseenter="selectedIndex = index">
                        <div class="size-8 rounded-lg bg-background border flex items-center justify-center shrink-0 shadow-sm transition-transform group-hover:scale-105"
                            :class="selectedIndex === index ? 'border-primary/30' : 'border-border/50'">
                            <FileText class="size-4"
                                :class="selectedIndex === index ? 'text-primary' : 'text-muted-foreground'" />
                        </div>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2">
                                <span class="font-semibold text-sm truncate">{{ result.title }}</span>
                                <span
                                    class="text-[10px] px-1.5 py-0.5 rounded-full bg-muted font-bold text-muted-foreground uppercase opacity-70">{{
                                        result.doctype_label || result.doctype }}</span>
                            </div>
                            <p class="text-[11px] text-muted-foreground truncate opacity-80">{{ result.subtitle }}</p>
                        </div>
                        <div v-if="selectedIndex === index"
                            class="shrink-0 flex items-center gap-1 text-[10px] font-bold text-primary/60">
                            <span>ENTER</span>
                            <CornerDownLeft class="size-3" />
                        </div>
                        <ChevronRight v-else class="size-4 text-muted-foreground/30" />
                    </button>
                </template>
            </div>

            <div
                class="flex items-center justify-between px-4 py-2 bg-muted/30 border-t text-[10px] text-muted-foreground font-medium">
                <div class="flex items-center gap-3">
                    <span class="flex items-center gap-1"><span class="border rounded px-1 bg-background">↑↓</span>
                        Навігація</span>
                    <span class="flex items-center gap-1"><span class="border rounded px-1 bg-background">↵</span>
                        Вибрати</span>
                </div>
                <div class="flex items-center gap-1">
                    <Command class="size-3" />
                    <span>K</span>
                </div>
            </div>
        </DialogContent>
    </Dialog>
</template>
