<script setup lang="ts">
/**
 * The current user's notification settings: which notifications (rules) come
 * through which channels. A switch turns a rule off in one channel; the first
 * row - every notification in that channel. A mandatory rule can't be turned
 * off. Saved at once (NotificationPreference rows).
 *
 * Opened from the profile (User → Preferences → Notification settings) and
 * from the bell: grunt.open_dialog('grunt/NotificationPreferences').
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Lock } from '@lucide/vue'
import { notificationsApi, type NotificationPreferences } from '@/core/api/notifications'
import { toast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const emit = defineEmits<{ close: [result?: unknown] }>()
const { t } = useI18n()

const data = ref<NotificationPreferences | null>(null)
const busy = ref(false)

const off = computed(() => {
  const set = new Set<string>()
  for (const row of data.value?.off ?? []) set.add(`${row.notification ?? ''}|${row.channel ?? ''}`)
  return set
})

function isOff(notification: string | null, channel: string): boolean {
  const n = notification ?? ''
  return off.value.has(`${n}|${channel}`) || off.value.has(`${n}|`)
}

/** Every notification is off in this channel (the first row). */
function allOff(channel: string): boolean {
  return isOff(null, channel)
}

async function load() {
  try {
    data.value = await notificationsApi.preferences()
  } catch (e: any) {
    toast.error(e?.message || t('Could not load the notification settings'))
    emit('close')
  }
}

async function toggle(notification: string | null, channel: string, enabled: boolean) {
  busy.value = true
  try {
    data.value = await notificationsApi.setPreference(channel, enabled, notification)
  } catch (e: any) {
    toast.error(e?.response?.data?.error?.message || e?.message || t('Could not save the setting'))
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-if="!data" class="flex justify-center py-10">
    <Spinner />
  </div>
  <div v-else class="flex flex-col gap-4">
    <p class="text-muted-foreground">
      {{ t('Choose which notifications you get, and through which channels. Mandatory ones can’t be turned off.') }}
    </p>
    <div class="max-h-[60vh] overflow-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('Notification') }}</TableHead>
            <TableHead v-for="c in data.channels" :key="c.value" class="text-center">{{ c.label }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell class="font-medium">{{ t('All notifications') }}</TableCell>
            <TableCell v-for="c in data.channels" :key="c.value" class="text-center">
              <Switch
                :model-value="!allOff(c.value)"
                :disabled="busy"
                :aria-label="`${t('All notifications')} · ${c.label}`"
                @update:model-value="(v: boolean) => toggle(null, c.value, v)"
              />
            </TableCell>
          </TableRow>
          <TableRow v-for="r in data.rules" :key="r.name">
            <TableCell>
              <span class="inline-flex items-center gap-1.5">
                {{ r.label }}
                <Lock v-if="r.mandatory" class="size-3.5 text-muted-foreground" :title="t('Mandatory')" />
              </span>
            </TableCell>
            <TableCell v-for="c in data.channels" :key="c.value" class="text-center">
              <span v-if="!r.channels.includes(c.value)" class="text-muted-foreground">—</span>
              <Switch
                v-else-if="r.mandatory"
                :model-value="true"
                disabled
                :title="t('Mandatory')"
                :aria-label="`${r.label} · ${c.label}`"
              />
              <Switch
                v-else
                :model-value="!allOff(c.value) && !isOff(r.name, c.value)"
                :disabled="busy || allOff(c.value)"
                :title="allOff(c.value) ? t('All notifications are off in this channel') : undefined"
                :aria-label="`${r.label} · ${c.label}`"
                @update:model-value="(v: boolean) => toggle(r.name, c.value, v)"
              />
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <div class="flex justify-end">
      <Button variant="outline" @click="emit('close')">{{ t('Close') }}</Button>
    </div>
  </div>
</template>
