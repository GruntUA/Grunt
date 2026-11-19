<script setup lang="ts">
/**
 * "Check access": why a user may (or may not) do something with a DocType or
 * one document - the trace of grunt.permissions.explain. Opened through
 * useAccessInspector() (form / list action `grunt.check_access`).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarClock, Check, CircleCheck, CircleX, Globe, Minus, Share2, ShieldQuestion, Users, X } from '@lucide/vue'
import type { DocField } from '@/types'
import { permissionsApi, type AccessTrace } from '@/core/api/permissions'
import { useAccessInspector } from '@/core/composables/useAccessInspector'
import { formatDate } from '@/core/datetime'
import LinkField from '@/components/fields/Link/Link.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const { t } = useI18n()
const { state } = useAccessInspector()

const ACTIONS = ['read', 'write', 'create', 'delete', 'share', 'print', 'export', 'import', 'report', 'select'] as const
const user = ref('')
const action = ref<string>('read')
const trace = ref<AccessTrace | null>(null)
const loading = ref(false)
const failed = ref('')

const userField = { fieldname: 'user', fieldtype: 'Link', label: '', options: 'User' } as DocField

watch(
  () => state.open,
  (open) => {
    if (!open) return
    trace.value = null
    failed.value = ''
    action.value = 'read'
  },
)

let request = 0
async function run() {
  if (!user.value || !state.doctype) return
  const mine = ++request
  loading.value = true
  failed.value = ''
  try {
    const result = await permissionsApi.explainAccess(user.value, state.doctype, action.value, state.name)
    if (mine === request) trace.value = result
  } catch (e) {
    if (mine === request) {
      trace.value = null
      failed.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    if (mine === request) loading.value = false
  }
}
watch([user, action], run)
watch(() => [state.doctype, state.name], () => { if (state.open) run() })

// The rules of the DocType that grant this action - the ones that matter here.
const grantingRules = computed(() => (trace.value?.rules ?? []).filter((r) => r.grants))
const missingRoles = computed(() => grantingRules.value.filter((r) => !r.held).map((r) => r.role))

function title(doctype: string | null, value: string): string {
  return (doctype && trace.value?.titles[`${doctype}/${value}`]) || value
}

function actionLabel(a: string): string {
  const labels: Record<string, string> = {
    read: t('Read'), write: t('Edit'), create: t('Create'), delete: t('Delete'), share: t('Share'),
    print: t('Print'), export: t('Export'), import: t('Import'), report: t('Report'), select: t('Select'),
  }
  return labels[a] ?? a
}

function shareVia(s: { via: string; role: string | null; user_group: string | null }): string {
  if (s.via === 'everyone') return t('with everyone')
  if (s.via === 'role') return t('with the role {role}', { role: s.role ?? '' })
  if (s.via === 'group') return t('with the group {group}', { group: s.user_group ?? '' })
  return t('with the user')
}
</script>

<template>
  <Dialog v-model:open="state.open">
    <DialogContent class="sm:max-w-2xl max-h-[90dvh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <ShieldQuestion class="size-4" />
          {{ t('Check access') }}
        </DialogTitle>
        <DialogDescription>
          {{ state.name ? t('Why a user may or may not act on {doctype} {name}.', { doctype: state.doctype, name: state.name }) : t('Why a user may or may not act on {doctype} documents.', { doctype: state.doctype }) }}
        </DialogDescription>
      </DialogHeader>

      <FieldGroup class="grid gap-4 sm:grid-cols-[1fr_12rem]">
        <Field>
          <FieldLabel>{{ t('User') }}</FieldLabel>
          <LinkField :field="userField" :model-value="user" @update:model-value="user = ($event as string) ?? ''" />
        </Field>
        <Field>
          <FieldLabel for="access-action">{{ t('Action') }}</FieldLabel>
          <NativeSelect id="access-action" v-model="action">
            <NativeSelectOption v-for="a in ACTIONS" :key="a" :value="a">{{ actionLabel(a) }}</NativeSelectOption>
          </NativeSelect>
        </Field>
      </FieldGroup>

      <div v-if="loading && !trace" class="flex justify-center py-6"><Spinner /></div>
      <Alert v-else-if="failed" variant="destructive">
        <CircleX />
        <AlertTitle>{{ t('Could not check access') }}</AlertTitle>
        <AlertDescription>{{ failed }}</AlertDescription>
      </Alert>

      <div v-else-if="trace" class="flex flex-col gap-5" :class="loading ? 'opacity-60' : undefined">
        <!-- Verdict -->
        <Alert :variant="trace.allowed ? 'default' : 'destructive'">
          <CircleCheck v-if="trace.allowed" />
          <CircleX v-else />
          <AlertTitle>
            {{ trace.allowed ? t('{user} may {action}', { user: trace.user_name, action: actionLabel(trace.action).toLowerCase() }) : t('{user} may not {action}', { user: trace.user_name, action: actionLabel(trace.action).toLowerCase() }) }}
          </AlertTitle>
          <AlertDescription v-if="!trace.allowed && missingRoles.length">
            {{ t('Access is given by the role: {roles}', { roles: missingRoles.join(', ') }) }}
          </AlertDescription>
        </Alert>

        <!-- Roles in force -->
        <section class="flex flex-col gap-2">
          <h3 class="text-sm font-medium">{{ t('Roles') }}</h3>
          <div v-if="trace.roles.length" class="flex flex-wrap gap-1.5">
            <Badge v-for="(r, i) in trace.roles" :key="i" variant="secondary" class="font-normal">
              {{ r.role }}
              <span v-if="r.scope_value" class="text-muted-foreground">· {{ t('within {value}', { value: title(r.scope_doctype, r.scope_value) }) }}</span>
              <span v-if="r.valid_to" class="text-muted-foreground">· {{ t('until {date}', { date: formatDate(r.valid_to) }) }}</span>
            </Badge>
          </div>
          <p v-else class="text-sm text-muted-foreground">{{ t('No roles') }}</p>
        </section>

        <!-- Child row / access_from -->
        <section v-if="trace.child || !trace.rules_decide" class="flex flex-col gap-2">
          <h3 class="text-sm font-medium">{{ trace.child ? t('Follows the parent document') : t('Follows the document it belongs to') }}</h3>
          <ul class="flex flex-col gap-1 text-sm">
            <li v-for="f in trace.followed" :key="f.field" class="flex items-center gap-2">
              <Check v-if="f.allowed" class="size-4 text-success" />
              <X v-else class="size-4 text-destructive" />
              {{ f.doctype }} {{ f.name }}
              <span class="text-muted-foreground">— {{ f.allowed ? t('can read') : t('cannot read') }}</span>
            </li>
          </ul>
          <p v-if="!trace.child && !trace.role_grants" class="text-sm text-muted-foreground">
            {{ t('No role of the user grants this action on the document type at all.') }}
          </p>
        </section>

        <!-- Rules -->
        <section v-if="!trace.child" class="flex flex-col gap-2">
          <h3 class="text-sm font-medium">{{ t('Rules that grant this action') }}</h3>
          <div v-if="grantingRules.length" class="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{{ t('Role') }}</TableHead>
                  <TableHead>{{ t('Condition') }}</TableHead>
                  <TableHead class="w-24 text-right">{{ trace.doc && trace.rules_decide ? t('This document') : '' }}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="r in grantingRules" :key="r.index" :class="r.held ? undefined : 'text-muted-foreground'">
                  <TableCell class="font-medium">
                    {{ r.role }}
                    <div v-if="!r.held" class="text-xs font-normal">{{ t('the user lacks this role') }}</div>
                  </TableCell>
                  <TableCell class="text-xs">
                    <code v-if="r.match">{{ r.match }}</code>
                    <span v-else-if="!r.scopes.length">{{ t('every document') }}</span>
                    <div v-for="sc in r.scopes" :key="sc.doctype">{{ t('within {doctype}: {values}', { doctype: sc.doctype, values: sc.values.map((v) => title(sc.doctype, v)).join(', ') }) }}</div>
                    <div v-if="r.unparseable" class="text-destructive">{{ t('condition cannot be applied - grants nothing') }}</div>
                  </TableCell>
                  <TableCell class="text-right">
                    <Check v-if="r.doc_ok === true" class="ml-auto size-4 text-success" :aria-label="t('passes')" />
                    <X v-else-if="r.doc_ok === false" class="ml-auto size-4 text-destructive" :aria-label="t('does not pass')" />
                    <Minus v-else class="ml-auto size-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
          <p v-else class="text-sm text-muted-foreground">{{ t('No rule of this document type grants this action.') }}</p>
        </section>

        <!-- Shares -->
        <section v-if="trace.doc && trace.shares.length" class="flex flex-col gap-2">
          <h3 class="text-sm font-medium">{{ t('Shared') }}</h3>
          <ul class="flex flex-col gap-1 text-sm">
            <li v-for="s in trace.shares" :key="s.name" class="flex items-center gap-2">
              <Globe v-if="s.via === 'everyone'" class="size-4" />
              <Users v-else-if="s.via === 'role' || s.via === 'group'" class="size-4" />
              <Share2 v-else class="size-4" />
              {{ shareVia(s) }}
              <Badge variant="outline" class="font-normal">{{ s.permission === 'Write' ? t('Edit') : t('Read') }}</Badge>
              <Badge v-if="s.valid_to" variant="outline" class="font-normal"><CalendarClock />{{ t('until {date}', { date: formatDate(s.valid_to) }) }}</Badge>
            </li>
          </ul>
        </section>

        <!-- Fields -->
        <section v-if="trace.hidden_fields.length || trace.readonly_fields.length" class="flex flex-col gap-1 text-sm">
          <h3 class="font-medium">{{ t('Fields') }}</h3>
          <p v-if="trace.hidden_fields.length">{{ t('Hidden: {fields}', { fields: trace.hidden_fields.join(', ') }) }}</p>
          <p v-if="trace.readonly_fields.length">{{ t('Read only: {fields}', { fields: trace.readonly_fields.join(', ') }) }}</p>
        </section>
      </div>
    </DialogContent>
  </Dialog>
</template>
