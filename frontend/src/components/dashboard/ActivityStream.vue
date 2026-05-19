<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/core/api/client'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useAuthStore } from '@/stores/auth'
import {
    FileText,
    Plus,
    RefreshCcw,
    Trash2,
    Clock,
    ExternalLink
} from '@lucide/vue'


interface ActivityEntry {
    id: string
    doctype: string
    doc_id: string
    action: string
    user: string
    details?: any
    created_at: string
}

const activities = ref<ActivityEntry[]>([])
const loading = ref(true)
const router = useRouter()
const auth = useAuthStore()

// WebSocket for real-time activity
const ws = useWebSocket('/api/v1/ws/public/site') // Connect to global site channel via public route
ws.onEvent('activity', (data: any) => {
    // Add to top and keep max 50
    activities.value = [data, ...activities.value].slice(0, 50)
})

async function fetchActivity() {
    loading.value = true
    try {
        const res = await api.get('/api/v1/method/grunt.activity.doctypes.ActivityLog.activity_log.list_activity')
        activities.value = res.data.data.items
    } catch {
        // silently ignore — empty state shown
    } finally {
        loading.value = false
    }
}

function getActionIcon(action: string) {
    switch (action.toLowerCase()) {
        case 'create': return Plus
        case 'update': return RefreshCcw
        case 'delete': return Trash2
        default: return FileText
    }
}

function getActionColor(action: string) {
    switch (action.toLowerCase()) {
        case 'create': return 'text-emerald-500 bg-emerald-500/10'
        case 'update': return 'text-amber-500 bg-amber-500/10'
        case 'delete': return 'text-rose-500 bg-rose-500/10'
        default: return 'text-blue-500 bg-blue-500/10'
    }
}

function formatTime(val: string) {
    const date = new Date(val)
    return date.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })
}

function formatDate(val: string) {
    const date = new Date(val)
    return date.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' })
}

function goToDoc(item: ActivityEntry) {
    // Need to find workspace. For now default to grunt or try to infer.
    router.push(`/grunt/${item.doctype}/${item.doc_id}`)
}

watch(() => auth.isLoggedIn, (loggedIn) => {
    if (loggedIn) fetchActivity()
}, { immediate: true })
</script>

<template>
    <div class="flex flex-col h-full bg-card border rounded-xl overflow-hidden shadow-sm">
        <div class="px-4 py-3 border-b flex items-center justify-between bg-muted/20">
            <div class="flex items-center gap-2">
                <Clock class="size-4 text-muted-foreground" />
                <h3 class="font-bold text-sm">Стрічка активності</h3>
            </div>
            <button @click="fetchActivity" class="text-xs text-primary hover:underline font-medium">Оновити</button>
        </div>

        <ScrollPanel class="flex-1">
            <div v-if="loading" class="flex flex-col items-center justify-center py-12 gap-3">
                <div class="size-5 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
                <span class="text-xs text-muted-foreground">Завантаження...</span>
            </div>

            <div v-else-if="activities.length === 0" class="py-12 text-center">
                <p class="text-sm text-muted-foreground">Немає недавньої активності</p>
            </div>

            <div v-else class="divide-y divide-border/50">
                <div v-for="item in activities" :key="item.id" class="p-4 hover:bg-muted/30 transition-colors group">
                    <div class="flex gap-3">
                        <div class="mt-0.5 size-8 rounded-lg flex items-center justify-center shrink-0"
                            :class="getActionColor(item.action)">
                            <component :is="getActionIcon(item.action)" class="size-4" />
                        </div>

                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between mb-1">
                                <span class="text-xs font-bold text-foreground">{{ item.user }}</span>
                                <span class="text-[10px] text-muted-foreground tabular-nums">{{
                                    formatTime(item.created_at) }}</span>
                            </div>

                            <p class="text-sm text-muted-foreground leading-snug break-words mb-2">
                                <span class="font-medium text-foreground">
                                    {{ item.action === 'create' ? 'Створив(ла)' : item.action === 'update' ?
                                        'Оновив(ла)' : item.action }}
                                </span>
                                документ
                                <span class="font-bold text-foreground/80 lowercase">{{ item.doctype }}</span>:
                                <span class="text-primary font-medium">{{ item.doc_id }}</span>
                            </p>

                            <div class="flex items-center justify-between">
                                <span
                                    class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono uppercase">{{
                                        formatDate(item.created_at) }}</span>
                                <button @click="goToDoc(item)"
                                    class="text-[10px] flex items-center gap-1 text-primary opacity-0 group-hover:opacity-100 transition-opacity font-bold uppercase tracking-wider">
                                    Переглянути
                                    <ExternalLink class="size-3" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </ScrollPanel>
    </div>
</template>
