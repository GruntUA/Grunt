<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/core/api/client'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useAuthStore } from '@/stores/auth'
import { formatTime as fmtTime, formatDayMonth } from '@/core/datetime'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
    FileText,
    Plus,
    RefreshCcw,
    Trash2,
    Clock,
    ExternalLink,
    History
} from '@lucide/vue'

const { t } = useI18n()


interface ActivityEntry {
    id: string
    ref_doctype: string
    doc_id: string
    title?: string
    action: string
    user: string
    user_name?: string
    details?: any
    created_at: string
}

const activities = ref<ActivityEntry[]>([])
const loading = ref(true)
const router = useRouter()
const auth = useAuthStore()

// WebSocket for real-time activity
// Authenticated site-wide channel - the activity feed carries user emails and
// document ids, so it must never ride the unauthenticated /ws/public/* route.
const ws = useWebSocket('/api/v1/ws/site')
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
        // silently ignore - empty state shown
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

function getActionTone(action: string) {
    switch (action.toLowerCase()) {
        case 'create': return 'bg-success/10 text-success'
        case 'update': return 'bg-warning/10 text-warning'
        case 'delete': return 'bg-destructive/10 text-destructive'
        default: return 'bg-info/10 text-info'
    }
}

function formatTime(val: string) {
    return fmtTime(val)
}

function formatDate(val: string) {
    return formatDayMonth(val)
}

function goToDoc(item: ActivityEntry) {
    // Need to find workspace. For now default to grunt or try to infer.
    router.push(`/grunt/${item.ref_doctype}/${item.doc_id}`)
}

watch(() => auth.isLoggedIn, (loggedIn) => {
    if (loggedIn) fetchActivity()
}, { immediate: true })
</script>

<template>
    <div class="flex h-full flex-col overflow-hidden rounded-lg border bg-card">
        <div class="flex items-center justify-between border-b px-4 py-2.5">
            <div class="flex items-center gap-2">
                <Clock class="size-3.5 text-muted-foreground" />
                <span class="font-semibold text-foreground">{{ t('Activity feed') }}</span>
            </div>
            <Button variant="ghost" size="icon-sm" :title="t('Refresh')" @click="fetchActivity">
                <RefreshCcw class="size-3.5" />
            </Button>
        </div>

        <div class="flex-1 overflow-y-auto">
            <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-12">
                <Spinner class="size-5 text-muted-foreground" />
                <span class="text-muted-foreground">{{ t('Loading...') }}</span>
            </div>

            <div v-else-if="activities.length === 0" class="flex flex-col items-center justify-center gap-2 py-12 text-center">
                <History class="size-6 text-muted-foreground/50" />
                <p class="text-muted-foreground">{{ t('No recent activity') }}</p>
            </div>

            <div v-else>
                <div v-for="item in activities" :key="item.id" class="group border-b px-4 py-3 transition-colors last:border-0 hover:bg-accent">
                    <div class="flex gap-3">
                        <div class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md" :class="getActionTone(item.action)">
                            <component :is="getActionIcon(item.action)" class="size-4" />
                        </div>

                        <div class="min-w-0 flex-1">
                            <div class="mb-1 flex items-center justify-between">
                                <span class="font-semibold text-foreground">{{ item.user_name || item.user }}</span>
                                <span class="tabular-nums text-muted-foreground">{{ formatTime(item.created_at) }}</span>
                            </div>

                            <p class="mb-2 break-words leading-snug text-muted-foreground">
                                <span class="font-medium text-foreground">
                                    {{ item.action === 'create' ? t('Created') : item.action === 'update' ?
                                        t('Updated') : item.action }}
                                </span>
                                {{ t('document') }}
                                <span class="font-semibold lowercase text-foreground/80">{{ item.ref_doctype }}</span>:
                                <span class="font-medium text-primary">{{ item.title || item.doc_id }}</span>
                            </p>

                            <div class="flex items-center justify-between">
                                <span class="rounded bg-muted px-1.5 py-0.5 font-mono uppercase text-muted-foreground">{{
                                    formatDate(item.created_at) }}</span>
                                <button type="button" class="flex items-center gap-1 font-semibold uppercase tracking-wider text-primary opacity-0 transition-opacity group-hover:opacity-100" @click="goToDoc(item)">
                                    {{ t('View') }}
                                    <ExternalLink class="size-3" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
