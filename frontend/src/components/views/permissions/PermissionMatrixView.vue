<script setup lang="ts">
/**
 * One role's permission rules on the DocTypes of the list page, as a matrix:
 * a line per rule (a role may hold several on one DocType, with different row
 * conditions), a column per action. Changes collect across pages and roles'
 * DocTypes until "Save" - which saves each changed DocType through the server
 * (grunt.api.v1.permission_matrix), with the DocType form's validation.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { docsApi } from '@/core/api/docs'
import {
  permissionsApi,
  type MatrixEdit,
  type MatrixRow,
  type MatrixRule,
} from '@/core/api/permissions'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import { docUrl } from '@/core/workspaceUrl'
import type { PermissionAction } from '@/types'

const props = defineProps<{
  rows: Record<string, unknown>[]
  workspace: string
  isLoading: boolean
  refreshKey: number
}>()

const { t } = useI18n()
const toast = useToast()
const dialog = useDialog()

// grunt/metadata/permission.py ACTIONS - the order Studio lists them in.
const ACTIONS: PermissionAction[] = [
  'read', 'select', 'write', 'create', 'delete', 'export', 'import', 'print', 'share', 'report',
]
// The role every user holds - not a Role document.
const ALL_ROLE = 'All'

const roles = ref<string[]>([])
const role = ref('')
const matrix = ref<Record<string, MatrixRow>>({})
const loading = ref(false)
const saving = ref(false)
// Changed lines only: line key -> the actions it will grant.
const draft = ref<Record<string, PermissionAction[]>>({})

interface Line {
  key: string
  doctype: string
  rule: MatrixRule | null
}

interface Group {
  doctype: string
  label: string
  isChild: boolean
  lines: Line[]
}

const lineKey = (doctype: string, rule: MatrixRule | null) =>
  `${doctype}\u0000${rule ? rule.index : 'new'}`

const doctypeNames = computed(() =>
  props.rows.map((r) => String(r.name ?? '')).filter(Boolean),
)

const groups = computed<Group[]>(() =>
  props.rows
    .filter((r) => r.name)
    .map((r) => {
      const doctype = String(r.name)
      const row = matrix.value[doctype]
      const rules = row?.rules ?? []
      const lines = (rules.length ? rules : [null]).map((rule) => ({
        key: lineKey(doctype, rule),
        doctype,
        rule,
      }))
      return {
        doctype,
        label: String(r.label || doctype),
        isChild: row?.is_child ?? false,
        lines,
      }
    }),
)

const dirtyCount = computed(() => Object.keys(draft.value).length)

function granted(line: Line): PermissionAction[] {
  return draft.value[line.key] ?? line.rule?.actions ?? []
}

function isOn(line: Line, action: PermissionAction): boolean {
  return granted(line).includes(action)
}

/** `select` comes with `read` - shown ticked and locked while `read` is. */
function impliedSelect(line: Line, action: PermissionAction): boolean {
  return action === 'select' && isOn(line, 'read')
}

function toggle(line: Line, action: PermissionAction, value: boolean | 'indeterminate') {
  const set = new Set(granted(line))
  if (value === true) set.add(action)
  else set.delete(action)
  const next = ACTIONS.filter((a) => set.has(a))
  const original = line.rule?.actions ?? []
  const nextDraft = { ...draft.value }
  if (next.join() === original.join()) delete nextDraft[line.key]
  else nextDraft[line.key] = next
  draft.value = nextDraft
}

function errorMessage(err: unknown): string {
  const data = (err as { response?: { data?: { error?: { message?: string }; detail?: unknown } } })
    ?.response?.data
  const detail = data?.error?.message ?? data?.detail
  return typeof detail === 'string' && detail ? detail : t('Could not save')
}

async function loadRoles() {
  try {
    const res = await docsApi.list('Role', { per_page: 500, sort: 'name', order: 'asc' })
    const names = res.data.map((r) => String(r.name))
    roles.value = [ALL_ROLE, ...names.filter((n) => n !== ALL_ROLE)]
  } catch {
    roles.value = [ALL_ROLE]
  }
}

async function loadMatrix() {
  const names = doctypeNames.value
  if (!role.value || !names.length) return
  loading.value = true
  try {
    const rows = await permissionsApi.getRoleMatrix(role.value, names)
    const next = { ...matrix.value }
    for (const row of rows) next[row.doctype] = row
    matrix.value = next
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}

// The select's value; `role` follows it unless unsaved changes are kept.
const roleChoice = ref('')
watch(roleChoice, async (next) => {
  if (next === role.value) return
  if (dirtyCount.value && !(await dialog.confirm(t('Discard unsaved permission changes?')))) {
    roleChoice.value = role.value
    return
  }
  draft.value = {}
  matrix.value = {}
  role.value = next
})

async function save() {
  // Group the changed lines by DocType: one save per DocType on the server.
  const byDoctype = new Map<string, MatrixEdit[]>()
  for (const [key, actions] of Object.entries(draft.value)) {
    const [doctype, index] = key.split('\u0000')
    const rule = matrix.value[doctype]?.rules.find((r) => String(r.index) === index) ?? null
    const edits = byDoctype.get(doctype) ?? []
    edits.push({ index: rule ? rule.index : null, match: rule?.match ?? null, actions })
    byDoctype.set(doctype, edits)
  }
  saving.value = true
  try {
    const rows = await permissionsApi.saveRoleMatrix(
      role.value,
      [...byDoctype].map(([doctype, rules]) => ({ doctype, rules })),
    )
    const next = { ...matrix.value }
    for (const row of rows) next[row.doctype] = row
    matrix.value = next
    draft.value = {}
    toast.success(t('Saved'))
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    saving.value = false
  }
}

function discard() {
  draft.value = {}
}

onMounted(loadRoles)
watch([role, () => doctypeNames.value.join('\u0000')], loadMatrix)
watch(
  () => props.refreshKey,
  (_v, old) => {
    if (old === undefined) return
    // Refresh re-reads every DocType of the page; unsaved changes stay.
    loadMatrix()
  },
)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-3">
    <div class="flex flex-wrap items-center gap-2">
      <NativeSelect
        v-model="roleChoice"
        size="sm"
        :aria-label="t('Role')"
      >
        <NativeSelectOption value="" disabled>{{ t('Choose a role') }}</NativeSelectOption>
        <NativeSelectOption v-for="r in roles" :key="r" :value="r">
          {{ r === ALL_ROLE ? t('All (every user)') : t(r) }}
        </NativeSelectOption>
      </NativeSelect>
      <Spinner v-if="loading" class="size-4" />
      <div class="ml-auto flex items-center gap-2">
        <span v-if="dirtyCount" class="text-sm text-muted-foreground">
          {{ t('Changed rules: {n}', { n: String(dirtyCount) }) }}
        </span>
        <Button v-if="dirtyCount" variant="outline" size="sm" :disabled="saving" @click="discard">
          {{ t('Discard') }}
        </Button>
        <Button size="sm" :disabled="!dirtyCount || saving" @click="save">
          <Spinner v-if="saving" class="size-4" />
          {{ t('Save') }}
        </Button>
      </div>
    </div>

    <Empty v-if="!role" class="flex-1">
      <EmptyHeader>
        <EmptyTitle>{{ t('Choose a role') }}</EmptyTitle>
        <EmptyDescription>
          {{ t('The matrix shows what the role may do with each document type of this page. Narrow the page with the list filters, e.g. by module.') }}
        </EmptyDescription>
      </EmptyHeader>
    </Empty>

    <div v-else-if="isLoading" class="flex flex-col gap-2">
      <Skeleton v-for="i in 8" :key="i" class="h-8 w-full" />
    </div>

    <div v-else class="min-h-0 flex-1 overflow-auto rounded-md border">
      <Table>
        <TableHeader class="sticky top-0 z-10 bg-background">
          <TableRow>
            <TableHead class="min-w-56">{{ t('Document type') }}</TableHead>
            <TableHead v-for="action in ACTIONS" :key="action" class="text-center">
              {{ t(action) }}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <template v-for="group in groups" :key="group.doctype">
            <TableRow v-for="(line, i) in group.lines" :key="line.key">
              <TableCell class="align-top">
                <template v-if="i === 0">
                  <RouterLink
                    :to="docUrl('DocType', group.doctype, workspace)"
                    class="font-medium hover:underline"
                  >
                    {{ t(group.label) }}
                  </RouterLink>
                  <div class="text-xs text-muted-foreground">{{ group.doctype }}</div>
                </template>
                <div v-if="line.rule?.match" class="mt-1">
                  <Badge variant="outline" :title="t('Row condition')">
                    {{ line.rule.match }}
                  </Badge>
                </div>
                <div
                  v-if="line.rule && (line.rule.hidden_fields.length || line.rule.readonly_fields.length)"
                  class="mt-1 text-xs text-muted-foreground"
                >
                  {{ t('Hidden fields: {n} · read-only: {m}', {
                    n: String(line.rule.hidden_fields.length),
                    m: String(line.rule.readonly_fields.length),
                  }) }}
                </div>
              </TableCell>
              <TableCell
                v-if="group.isChild"
                :colspan="ACTIONS.length"
                class="text-sm text-muted-foreground"
              >
                {{ t('A table inside other documents: access follows the document that holds it') }}
              </TableCell>
              <template v-else>
                <TableCell v-for="action in ACTIONS" :key="action" class="text-center">
                  <Checkbox
                    :model-value="isOn(line, action) || impliedSelect(line, action)"
                    :disabled="saving || impliedSelect(line, action)"
                    :title="impliedSelect(line, action) ? t('Included in read') : undefined"
                    :aria-label="`${t(group.label)}: ${t(action)}`"
                    @update:model-value="(v) => toggle(line, action, v)"
                  />
                </TableCell>
              </template>
            </TableRow>
          </template>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
