<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { Share2, X } from '@lucide/vue'
import type { DocField } from '@/types'
import type { ShareTarget } from '@/core/api/docs'
import type { DocSidebarState } from './useDocSidebar'
import SidebarUserCommand from './SidebarUserCommand.vue'
import LinkField from '@/components/fields/Link/Link.vue'
import DateField from '@/components/fields/Date/Date.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Item, ItemActions, ItemContent, ItemMedia, ItemTitle } from '@/components/ui/item'
import { Spinner } from '@/components/ui/spinner'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const props = defineProps<{
  sb: DocSidebarState
  /** May hand out Edit - the user can write the document themselves. */
  canWrite: boolean
  /** Users who already have a share of their own. */
  exclude?: string[]
}>()
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ shared: [] }>()

const { t } = useI18n()

type Kind = 'user' | 'role' | 'group' | 'everyone'
const kind = ref<Kind>('user')
const user = ref('')
const role = ref('')
const group = ref('')
const permission = ref<'Read' | 'Write'>('Read')
const canReshare = ref(false)
const validTo = ref<string | null>(null)
const saving = ref(false)
// Each opening is a session: a request still running from an earlier one
// must not close (and drop the input of) the dialog opened again since.
let session = 0

watch(open, (v) => {
  if (!v) return
  session += 1
  saving.value = false
  kind.value = 'user'
  user.value = ''
  role.value = ''
  group.value = ''
  permission.value = 'Read'
  canReshare.value = false
  validTo.value = null
})

const roleField = { fieldname: 'role', fieldtype: 'Link', label: '', options: 'Role' } as DocField
const groupField = { fieldname: 'user_group', fieldtype: 'Link', label: '', options: 'UserGroup' } as DocField
const dateField = { fieldname: 'valid_to', fieldtype: 'Date', label: '' } as DocField

const ready = computed(() => {
  if (kind.value === 'user') return !!user.value
  if (kind.value === 'role') return !!role.value
  if (kind.value === 'group') return !!group.value
  return true
})

async function submit() {
  if (!ready.value) return
  const target: ShareTarget = {
    permission: permission.value,
    can_reshare: canReshare.value,
    valid_to: validTo.value || null,
  }
  if (kind.value === 'user') target.user = user.value
  else if (kind.value === 'role') target.role = role.value
  else if (kind.value === 'group') target.user_group = group.value
  else target.everyone = true
  const mine = session
  saving.value = true
  try {
    await props.sb.share(target)
    if (mine !== session) return
    open.value = false
    emit('shared')
  } catch {
    /* the request layer shows the error */
  } finally {
    if (mine === session) saving.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ t('Share document') }}</DialogTitle>
        <DialogDescription>{{ t('Give access to this document to a user, everyone holding a role, the members of a group, or every user.') }}</DialogDescription>
      </DialogHeader>

      <FieldGroup>
        <Field>
          <FieldLabel>{{ t('With whom') }}</FieldLabel>
          <ToggleGroup
            :model-value="kind"
            type="single"
            variant="outline"
            class="w-full"
            @update:model-value="(v) => { if (v) kind = v as Kind }"
          >
            <ToggleGroupItem value="user" class="flex-1">{{ t('User') }}</ToggleGroupItem>
            <ToggleGroupItem value="role" class="flex-1">{{ t('Role') }}</ToggleGroupItem>
            <ToggleGroupItem value="group" class="flex-1">{{ t('Group') }}</ToggleGroupItem>
            <ToggleGroupItem value="everyone" class="flex-1">{{ t('Everyone') }}</ToggleGroupItem>
          </ToggleGroup>
        </Field>

        <Field v-if="kind === 'user'">
          <FieldLabel>{{ t('User') }}</FieldLabel>
          <div class="rounded-md border">
            <SidebarUserCommand v-if="!user" :sb="sb" :exclude="exclude" @select="user = $event" />
            <Item v-else size="sm" class="flex-nowrap gap-2 px-2 py-1.5">
              <ItemMedia>
                <Avatar class="size-6">
                  <AvatarImage v-if="sb.personAvatar(user)" :src="sb.personAvatar(user)!" />
                  <AvatarFallback class="text-[10px]">{{ sb.personInitials(user) }}</AvatarFallback>
                </Avatar>
              </ItemMedia>
              <ItemContent class="min-w-0">
                <ItemTitle class="w-full font-normal"><span class="truncate">{{ sb.personName(user) }}</span></ItemTitle>
              </ItemContent>
              <ItemActions>
                <Button variant="ghost" size="icon-xs" :aria-label="t('Change')" @click="user = ''">
                  <X />
                </Button>
              </ItemActions>
            </Item>
          </div>
        </Field>

        <Field v-else-if="kind === 'role'">
          <FieldLabel>{{ t('Role') }}</FieldLabel>
          <LinkField :field="roleField" :model-value="role" @update:model-value="role = ($event as string) ?? ''" />
          <FieldDescription>{{ t('Everyone holding the role gets access, whatever the scope of their role.') }}</FieldDescription>
        </Field>

        <Field v-else-if="kind === 'group'">
          <FieldLabel>{{ t('User group') }}</FieldLabel>
          <LinkField :field="groupField" :model-value="group" @update:model-value="group = ($event as string) ?? ''" />
          <FieldDescription>{{ t('Every member of the group gets access, including those added later.') }}</FieldDescription>
        </Field>

        <FieldDescription v-else>{{ t('Every signed-in user gets access. Nobody is notified.') }}</FieldDescription>

        <Field>
          <FieldLabel>{{ t('Access') }}</FieldLabel>
          <ToggleGroup
            :model-value="permission"
            type="single"
            variant="outline"
            class="w-full"
            @update:model-value="(v) => { if (v) permission = v as 'Read' | 'Write' }"
          >
            <ToggleGroupItem value="Read" class="flex-1">{{ t('Read') }}</ToggleGroupItem>
            <ToggleGroupItem value="Write" class="flex-1" :disabled="!canWrite">{{ t('Edit') }}</ToggleGroupItem>
          </ToggleGroup>
        </Field>

        <Field>
          <FieldLabel>{{ t('Valid until') }}</FieldLabel>
          <DateField :field="dateField" :model-value="validTo" @update:model-value="validTo = ($event as string) || null" />
          <FieldDescription>{{ t('Inclusive. Leave empty for no end date.') }}</FieldDescription>
        </Field>

        <Field orientation="horizontal">
          <Checkbox id="share-can-reshare" :model-value="canReshare" @update:model-value="(v) => canReshare = v === true" />
          <FieldLabel for="share-can-reshare" class="font-normal">{{ t('Can share further') }}</FieldLabel>
        </Field>
      </FieldGroup>

      <DialogFooter>
        <Button variant="outline" @click="open = false">{{ t('Cancel') }}</Button>
        <Button :disabled="!ready || saving" @click="submit">
          <Spinner v-if="saving" />
          <Share2 v-else />
          {{ t('Share') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
