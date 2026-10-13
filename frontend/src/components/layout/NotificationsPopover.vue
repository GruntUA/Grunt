<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Bell, BellDot, Check, CheckCheck, BellOff, BellRing } from '@lucide/vue'
import { formatIntl } from '@/core/datetime'
import { useWebPush } from '@/core/composables/useWebPush'

const { isSupported: pushSupported, isSubscribed: pushSubscribed, isLoading: pushLoading, permissionState: pushPermission, subscribe: pushSubscribe, unsubscribe: pushUnsubscribe } = useWebPush()

import { type NotificationItem, notificationsApi } from '@/core/api/notifications'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useToast } from '@/core/composables/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { docUrl } from '@/core/workspaceUrl'
import { SidebarMenuBadge, SidebarMenuButton } from '@/components/ui/sidebar'

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

    if (n.ref_doctype && n.doc_id) {
        isOpen.value = false
        router.push(docUrl(n.ref_doctype, n.doc_id, props.workspace))
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
        <SidebarMenuButton :tooltip="t('Notifications')" @click="toggle">
            <component :is="unreadCount > 0 ? BellDot : Bell" />
            <span>{{ t('Notifications') }}</span>
        </SidebarMenuButton>
        <SidebarMenuBadge v-if="unreadCount > 0">{{ unreadCount }}</SidebarMenuBadge>

        <Popover v-model:open="isOpen">
            <PopoverAnchor :reference="anchorEl ?? undefined" />
            <PopoverContent align="start" class="w-96 max-w-[calc(100vw-2rem)] p-0">
                <div class="flex flex-col overflow-hidden">
                    <!-- Header -->
                    <div class="flex items-center justify-between px-3 py-2 border-b">
                        <div class="flex items-center gap-2">
                            <h3 class="font-semibold">{{ t('Notifications') }}</h3>
                            <Badge v-if="unreadCount > 0" variant="secondary" class="h-4 px-1.5 tabular-nums">
                                {{ unreadCount }}
                            </Badge>
                        </div>
                        <Button v-if="unreadCount > 0" variant="ghost" size="icon"
                            class="size-7 text-muted-foreground" @click="markAllAsRead"
                            :title="t('Mark all as read')" :aria-label="t('Mark all as read')">
                            <CheckCheck class="size-4" />
                        </Button>
                    </div>

                    <!-- List -->
                    <div class="max-h-[320px] w-full overflow-y-auto">
                        <div v-if="notifications.length === 0"
                            class="flex flex-col items-center justify-center gap-1 py-12 text-center px-4">
                            <Bell class="size-8 text-muted-foreground/25 mb-1" />
                            <p class="font-medium text-foreground">{{ t('No notifications') }}</p>
                            <p class="text-muted-foreground">{{ t('Your latest notifications will appear here.') }}</p>
                        </div>
                        <div v-else class="flex flex-col divide-y divide-border/60">
                            <div v-for="n in notifications" :key="n.id"
                                class="group flex items-start gap-2.5 px-3 py-2.5 transition-colors cursor-pointer"
                                :class="n.is_read ? 'hover:bg-muted/50' : 'bg-primary/[0.04] hover:bg-primary/[0.08]'"
                                @click="handleNotificationClick(n)">
                                <span class="mt-1.5 size-1.5 shrink-0 rounded-full"
                                    :class="n.is_read ? 'bg-transparent' : 'bg-primary'" />
                                <div class="flex-1 min-w-0">
                                    <p class="font-medium leading-snug line-clamp-2"
                                        :class="n.is_read ? 'text-muted-foreground' : 'text-foreground'">
                                        {{ n.subject }}
                                    </p>
                                    <p v-if="n.message" class="text-muted-foreground line-clamp-2 leading-snug mt-0.5">
                                        {{ n.message }}
                                    </p>
                                    <div class="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground/70 min-w-0">
                                        <span class="shrink-0">{{ formatDate(n.created_at) }}</span>
                                        <template v-if="n.ref_doctype">
                                            <span aria-hidden="true">·</span>
                                            <span class="truncate">{{ n.ref_doctype }}</span>
                                        </template>
                                    </div>
                                </div>
                                <Button v-if="!n.is_read" variant="ghost" size="icon-xs"
                                    class="text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                                    :title="t('Mark as read')" :aria-label="t('Mark as read')"
                                    @click.stop="markAsRead(n.id)">
                                    <Check />
                                </Button>
                            </div>
                        </div>
                    </div>

                    <!-- Push subscribe footer -->
                    <div v-if="pushSupported" class="flex items-center justify-between gap-2 border-t bg-muted/30 px-3 py-2">
                        <span class="text-xs text-muted-foreground">
                            <template v-if="pushPermission === 'denied'">{{ t('Notifications are blocked in the browser settings for this site') }}</template>
                            <template v-else>{{ pushSubscribed ? t('Push notifications enabled') : t('Push notifications disabled') }}</template>
                        </span>
                        <Button v-if="pushPermission !== 'denied'" :variant="pushSubscribed ? 'ghost' : 'outline'" size="sm"
                            class="h-7 shrink-0 gap-1.5 px-2.5" :disabled="pushLoading"
                            @click="pushSubscribed ? pushUnsubscribe() : pushSubscribe()">
                            <BellOff v-if="pushSubscribed" class="size-3.5" />
                            <BellRing v-else class="size-3.5" />
                            {{ pushSubscribed ? t('Disable') : t('Enable') }}
                        </Button>
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    </div>
</template>
