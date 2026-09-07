<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Bell, Check, BellOff, BellRing } from '@lucide/vue'
import { formatIntl } from '@/core/datetime'
import { useWebPush } from '@/core/composables/useWebPush'

const { isSupported: pushSupported, isSubscribed: pushSubscribed, isLoading: pushLoading, subscribe: pushSubscribe, unsubscribe: pushUnsubscribe } = useWebPush()

import { type NotificationItem, notificationsApi } from '@/core/api/notifications'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useToast } from '@/core/composables/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'

const props = defineProps<{
    workspace?: string
}>()

const { t } = useI18n()
const router = useRouter()
const toast = useToast()
const notifications = ref<NotificationItem[]>([])
const unreadCount = ref(0)
const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)

// WebSocket for real-time notifications
const ws = useWebSocket('/api/v1/ws/user')
ws.onEvent('notification', (data: any) => {
    fetchNotifications()
    toast.info(data.subject || t('New notification'))
})

async function fetchNotifications() {
    try {
        const list = await notificationsApi.list({ limit: 50 })
        notifications.value = list
        unreadCount.value = list.filter(n => !n.is_read).length
    } catch (error) {
        console.error('Failed to fetch notifications', error)
    }
}

async function markAllAsRead() {
    await notificationsApi.markAllRead()
    await fetchNotifications()
}

async function markAsRead(id: string) {
    await notificationsApi.markRead(id)
    await fetchNotifications()
}

function handleNotificationClick(n: NotificationItem) {
    if (!n.is_read) {
        markAsRead(n.id)
    }

    if (n.doctype && n.doc_id) {
        isOpen.value = false
        const ws = props.workspace || 'grunt'
        router.push(`/${ws}/${n.doctype}/${n.doc_id}`)
    }
}

function formatDate(val: string) {
    return formatIntl(val, {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
    })
}

function toggle(event: Event) {
    anchorEl.value = event.currentTarget as HTMLElement
    isOpen.value = !isOpen.value
}

onMounted(() => {
    fetchNotifications()
})

onUnmounted(() => {
    // ws handles itself via useWebSocket onUnmounted
})
</script>

<template>
    <div>
        <button class="relative w-full flex items-center justify-between px-3 py-2 rounded-lg transition-all group"
            :class="unreadCount > 0 ? 'bg-primary/5 hover:bg-primary/10 text-primary' : 'hover:bg-muted/50 text-muted-foreground hover:text-foreground'"
            @click="toggle">
            <div class="flex items-center gap-2.5 min-w-0">
                <div class="relative flex items-center justify-center shrink-0">
                    <Bell class="size-4 transition-colors" />
                    <span v-if="unreadCount > 0" class="absolute -top-1 -right-1 flex h-2 w-2">
                        <span
                            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                    </span>
                </div>
                <span class="font-medium truncate">{{ t('Notifications') }}</span>
            </div>
            <Badge v-if="unreadCount > 0" class="h-5 px-1.5 text-xs font-semibold tabular-nums">
                {{ unreadCount }}
            </Badge>
        </button>

        <Popover v-model:open="isOpen">
            <PopoverAnchor :reference="anchorEl ?? undefined" />
            <PopoverContent align="start" class="w-80 p-0">
                <div class="flex flex-col overflow-hidden text-xs">
                    <!-- Header -->
                    <div class="flex items-center justify-between px-3 py-2 border-b">
                        <div class="flex items-center gap-2">
                            <h3 class="font-semibold">{{ t('Notifications') }}</h3>
                            <Badge v-if="unreadCount > 0" variant="secondary" class="h-4 px-1.5 tabular-nums">
                                {{ unreadCount }}
                            </Badge>
                        </div>
                        <Button v-if="unreadCount > 0" variant="ghost" size="sm"
                            class="h-6 gap-1 px-1.5 text-muted-foreground" @click="markAllAsRead"
                            :title="t('Mark all as read')">
                            <Check class="size-3.5" />
                            {{ t('Mark all as read') }}
                        </Button>
                    </div>

                    <!-- List -->
                    <div class="max-h-[320px] w-full overflow-y-auto">
                        <div v-if="notifications.length === 0"
                            class="flex flex-col items-center justify-center gap-1 py-12 text-center px-4">
                            <Bell class="size-8 text-muted-foreground/25 mb-1" />
                            <p class="font-medium text-foreground">{{ t('No notifications') }}</p>
                            <p class="text-muted-foreground">Тут з'являться ваші останні сповіщення.</p>
                        </div>
                        <div v-else class="flex flex-col divide-y divide-border/60">
                            <div v-for="n in notifications" :key="n.id"
                                class="group flex items-start gap-2.5 px-3 py-2.5 transition-colors cursor-pointer"
                                :class="n.is_read ? 'hover:bg-muted/50' : 'bg-primary/[0.04] hover:bg-primary/[0.08]'"
                                @click="handleNotificationClick(n)">
                                <span class="mt-1.5 size-1.5 shrink-0 rounded-full"
                                    :class="n.is_read ? 'bg-transparent' : 'bg-primary'" />
                                <div class="flex-1 min-w-0">
                                    <p class="font-semibold leading-snug line-clamp-2"
                                        :class="n.is_read ? 'text-muted-foreground' : 'text-foreground'">
                                        {{ n.subject }}
                                    </p>
                                    <p v-if="n.message" class="text-muted-foreground line-clamp-2 leading-snug mt-0.5">
                                        {{ n.message }}
                                    </p>
                                    <div class="flex items-center gap-2 mt-1 text-muted-foreground/70">
                                        <span>{{ formatDate(n.created_at) }}</span>
                                        <span v-if="n.doctype" class="uppercase tracking-wide">{{ n.doctype }}</span>
                                    </div>
                                </div>
                                <button v-if="!n.is_read"
                                    class="shrink-0 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover:opacity-100"
                                    @click.stop="markAsRead(n.id)" :title="t('Mark as read')">
                                    <Check class="size-3.5" />
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Push subscribe footer -->
                    <div v-if="pushSupported" class="px-3 py-2 border-t flex items-center justify-between">
                        <span class="text-muted-foreground">
                            {{ pushSubscribed ? t('Push notifications enabled') : t('Push notifications disabled') }}
                        </span>
                        <Button variant="ghost" size="sm" class="h-6 px-2" :disabled="pushLoading"
                            @click="pushSubscribed ? pushUnsubscribe() : pushSubscribe()">
                            <BellOff v-if="pushSubscribed" class="size-3 mr-1" />
                            <BellRing v-else class="size-3 mr-1" />
                            {{ pushSubscribed ? t('Disable') : t('Enable') }}
                        </Button>
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    </div>
</template>
