<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Component } from 'vue'
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from '@lucide/vue'
import { useDialog } from '@/core/composables/useDialog'
import LinkField from '@/components/fields/Link/Link.vue'
import PasswordField from '@/components/fields/Password/Password.vue'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Spinner } from '@/components/ui/spinner'
import { DialogFooter } from '@/components/ui/dialog'
const { state, close } = useDialog()

const MSG_ICON_MAP: Record<string, { icon: Component; class: string }> = {
  green: { icon: CheckCircle2, class: 'text-green-600 dark:text-green-500' },
  success: { icon: CheckCircle2, class: 'text-green-600 dark:text-green-500' },
  red: { icon: AlertCircle, class: 'text-destructive' },
  error: { icon: AlertCircle, class: 'text-destructive' },
  orange: { icon: AlertTriangle, class: 'text-amber-500' },
  yellow: { icon: AlertTriangle, class: 'text-amber-500' },
  warning: { icon: AlertTriangle, class: 'text-amber-500' },
  blue: { icon: Info, class: 'text-primary' },
  info: { icon: Info, class: 'text-primary' },
}
const msgIndicator = computed(() => MSG_ICON_MAP[String(state.indicator ?? '')] ?? null)

const promptValue = ref('')
const formValues = ref<Record<string, any>>({})
const copiedField = ref<string | null>(null)
const tableSearch = ref<Record<string, string>>({})

async function copyToClipboard(fieldname: string, value: string) {
  try {
    await navigator.clipboard.writeText(value)
    copiedField.value = fieldname
    setTimeout(() => { copiedField.value = null }, 2000)
  } catch {
    // fallback: select text in the textarea
  }
}

function reseedFormValues() {
  const vals: Record<string, any> = {}
  const search: Record<string, string> = {}
  state.fields.forEach(f => {
    if (f.fieldtype === 'Table') {
      vals[f.fieldname] = f.multiple === false ? (f.default ?? null) : (Array.isArray(f.default) ? f.default : [])
      search[f.fieldname] = ''
    } else {
      vals[f.fieldname] = f.default ?? (f.fieldtype === 'Check' ? false : '')
    }
  })
  formValues.value = vals
  tableSearch.value = search
}

// ── Table field helpers ─────────────────────────────────────────────────
function rowKeyOf(f: any, row: any): string {
  return String(row?.[f.rowKey || 'name'] ?? '')
}
function filteredRows(f: any): any[] {
  const rows: any[] = f.rows || []
  const q = (tableSearch.value[f.fieldname] || '').toLowerCase().trim()
  if (!q) return rows
  const cols = f.columns || []
  return rows.filter(r => cols.some((c: any) => String(r[c.key] ?? '').toLowerCase().includes(q)))
}
function isRowSelected(f: any, row: any): boolean {
  const v = formValues.value[f.fieldname]
  const k = rowKeyOf(f, row)
  if (f.multiple === false) return !!v && rowKeyOf(f, v) === k
  return Array.isArray(v) && v.some((r: any) => rowKeyOf(f, r) === k)
}
function toggleRow(f: any, row: any) {
  const k = rowKeyOf(f, row)
  if (f.multiple === false) {
    formValues.value[f.fieldname] = isRowSelected(f, row) ? null : row
    return
  }
  const cur: any[] = Array.isArray(formValues.value[f.fieldname]) ? formValues.value[f.fieldname] : []
  formValues.value[f.fieldname] = isRowSelected(f, row)
    ? cur.filter(r => rowKeyOf(f, r) !== k)
    : [...cur, row]
}
function allSelected(f: any): boolean {
  const rows = filteredRows(f)
  return rows.length > 0 && rows.every(r => isRowSelected(f, r))
}
function toggleAll(f: any) {
  const rows = filteredRows(f)
  const cur: any[] = Array.isArray(formValues.value[f.fieldname]) ? formValues.value[f.fieldname] : []
  if (allSelected(f)) {
    const drop = new Set(rows.map(r => rowKeyOf(f, r)))
    formValues.value[f.fieldname] = cur.filter(r => !drop.has(rowKeyOf(f, r)))
  } else {
    const have = new Set(cur.map(r => rowKeyOf(f, r)))
    formValues.value[f.fieldname] = [...cur, ...rows.filter(r => !have.has(rowKeyOf(f, r)))]
  }
}
function selectedCount(f: any): number {
  const v = formValues.value[f.fieldname]
  return Array.isArray(v) ? v.length : v ? 1 : 0
}
function isSelectable(f: any): boolean {
  return f.selectable === undefined ? f.multiple !== false : !!f.selectable
}
function askConfirm(message: string): Promise<boolean> {
  return new Promise<boolean>((res) => { state.actionConfirm = { message, resolve: res } })
}
async function handleRowAction(f: any, row: any, actIdx: number) {
  const act = f.rowActions?.[actIdx]
  if (!act || state.busyButton !== null) return
  state.busyButton = -1 // block other buttons during a row action
  try {
    await act.onClick(row, {
      confirm: askConfirm,
      setRows: (rows: any[]) => { f.rows = rows },
    })
  } catch (e) {
    console.error('Row action failed', e)
  } finally {
    state.busyButton = null
  }
}

watch(() => state.open, (v) => {
  if (v) {
    if (state.type === 'prompt' && state.fields.length > 0) {
      promptValue.value = String(state.fields[0].default ?? '')
    } else if (state.type === 'dialog') {
      reseedFormValues()
    }
  }
})

async function handleAction(idx: number) {
  const btn = state.buttons[idx]
  if (!btn || state.busyButton !== null) return
  state.busyButton = idx
  try {
    return await btn.action({
      values: { ...formValues.value },
      setField: (fieldname, patch) => {
        const f = state.fields.find(x => x.fieldname === fieldname)
        if (!f) return
        Object.assign(f, patch)
        // keep the live input value in sync when `default` is rewritten
        if ('default' in patch) formValues.value[fieldname] = patch.default
        if (patch.options !== undefined && !(patch.options ?? '').split('\n').includes(String(formValues.value[fieldname] ?? ''))) {
          formValues.value[fieldname] = ''
        }
      },
      setFields: (fields) => {
        state.fields = fields as any
        reseedFormValues()
      },
      confirm: askConfirm,
      close: (value?: unknown) => close(value),
    })
  } catch (e) {
    console.error('Dialog action failed', e)
  } finally {
    state.busyButton = null
  }
}

function resolveActionConfirm(v: boolean) {
  const r = state.actionConfirm?.resolve
  state.actionConfirm = null
  r?.(v)
}

function onConfirm() {
  if (state.type === 'confirm') close(true)
  else if (state.type === 'prompt') close(promptValue.value || null)
  else if (state.type === 'dialog') close({ ...formValues.value })
  else close()
}

function onCancel() {
  if (state.type === 'confirm') close(false)
  else if (state.type === 'prompt') close(null)
  else close()
}

function onOpenChange(v: boolean) {
  if (!v) onCancel()
}
</script>

<template>
  <Dialog :open="state.open" @update:open="(v: boolean) => { state.open = v; if (!v) onOpenChange(false) }">
    <DialogContent
      class="p-0 px-6 pb-4 pt-2"
      :class="{
        'sm:max-w-md': state.size === 'small',
        'sm:max-w-lg': state.size === 'large',
        'sm:max-w-2xl': state.size === 'extra-large',
      }"
    >
    <DialogHeader v-if="state.title">
      <DialogTitle class="font-semibold flex items-center gap-2">
        <span v-if="state.indicator && !(state.type === 'msgprint' && msgIndicator)"
          class="inline-block w-2.5 h-2.5 rounded-full shrink-0"
          :style="{ backgroundColor: state.indicator }" />
        {{ state.title }}
      </DialogTitle>
    </DialogHeader>
    <DialogTitle v-else class="sr-only">Діалог</DialogTitle>
    <DialogDescription class="sr-only">Dialog content</DialogDescription>

    <!-- Content -->
    <div>
        <!-- Msgprint -->
        <div v-if="state.type === 'msgprint'" class="flex gap-3 py-2">
            <component :is="msgIndicator?.icon" v-if="msgIndicator" class="size-5 shrink-0 mt-px" :class="msgIndicator?.class" />
            <div class="text-foreground/85 leading-relaxed whitespace-pre-wrap [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2"
                v-html="state.message" />
        </div>

        <!-- Confirm -->
        <p v-else-if="state.type === 'confirm'" class="text-muted-foreground py-2">{{ state.message }}</p>

        <!-- Prompt -->
        <div v-else-if="state.type === 'prompt'" class="space-y-2 py-2">
            <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
                <label :for="field.fieldname" class="font-medium text-foreground">{{ field.label }}</label>
                <div v-if="field.fieldtype === 'HTML'" v-html="field.default" class="rounded border p-2 bg-muted/30" />
                <Input v-else :id="field.fieldname" v-model="promptValue" :placeholder="field.placeholder"
                    :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
                    class="w-full"
                    @keydown.enter="onConfirm" />
            </div>
        </div>

        <!-- Custom Dialog (grunt.form) -->
        <div v-else-if="state.type === 'dialog'" class="space-y-4 py-2">
            <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
                <template v-if="field.fieldtype === 'HTML'">
                    <label v-if="field.label" class="mb-1 block font-medium text-foreground">{{ field.label }}</label>
                    <div v-if="field.plain" v-html="String(field.default || '')"
                        class="text-foreground/85 leading-relaxed [&_a]:text-primary [&_a]:underline" />
                    <div v-else v-html="String(field.default || '').replace(/<\?xml.*\?>/g, '')"
                        class="rounded-lg border-2 border-dashed p-6 flex justify-center bg-muted shadow-inner min-h-[240px] items-center [&>svg]:block [&>svg]:max-w-full [&>svg]:h-auto" />
                </template>
                <template v-else-if="field.fieldtype === 'Table'">
                    <label v-if="field.label" class="font-medium text-foreground">{{ field.label }}</label>
                    <p v-if="field.description" class="text-muted-foreground -mt-1">{{ field.description }}</p>
                    <Input
                        v-if="field.searchable !== false"
                        v-model="tableSearch[field.fieldname]"
                        placeholder="Пошук…"
                        class="w-full mb-2"
                    />
                    <div class="rounded-md border border-border overflow-hidden">
                        <div class="overflow-auto" :style="{ maxHeight: field.maxHeight || '320px' }">
                            <table class="w-full text-sm border-collapse">
                                <thead class="bg-muted/60 sticky top-0 z-10">
                                    <tr>
                                        <th v-if="isSelectable(field)" class="w-9 px-2 py-2">
                                            <Checkbox
                                                v-if="field.multiple !== false"
                                                :model-value="allSelected(field)"
                                                @update:model-value="toggleAll(field)"
                                            />
                                        </th>
                                        <th
                                            v-for="c in field.columns"
                                            :key="c.key"
                                            class="px-3 py-2 font-medium text-muted-foreground whitespace-nowrap"
                                            :style="{ textAlign: c.align || 'left', width: c.width }"
                                        >{{ c.label }}</th>
                                        <th v-if="field.rowActions?.length" class="w-px px-3 py-2"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr
                                        v-for="row in filteredRows(field)"
                                        :key="rowKeyOf(field, row)"
                                        class="border-t border-border transition-colors"
                                        :class="[
                                            isSelectable(field) ? 'cursor-pointer hover:bg-muted/40' : '',
                                            isRowSelected(field, row) ? 'bg-primary/5' : '',
                                        ]"
                                        @click="isSelectable(field) && toggleRow(field, row)"
                                    >
                                        <td v-if="isSelectable(field)" class="px-2 py-1.5 text-center" @click.stop>
                                            <Checkbox
                                                :model-value="isRowSelected(field, row)"
                                                @update:model-value="toggleRow(field, row)"
                                            />
                                        </td>
                                        <td
                                            v-for="c in field.columns"
                                            :key="c.key"
                                            class="px-3 py-2 align-top"
                                            :style="{ textAlign: c.align || 'left' }"
                                        >
                                            <span v-if="c.format" v-html="c.format(row[c.key], row)" />
                                            <template v-else>{{ row[c.key] ?? '—' }}</template>
                                        </td>
                                        <td v-if="field.rowActions?.length" class="px-3 py-1.5 text-right whitespace-nowrap" @click.stop>
                                            <Button
                                                v-for="(act, ai) in field.rowActions"
                                                :key="ai"
                                                :variant="act.variant ?? 'ghost'"
                                                size="sm"
                                                :disabled="state.busyButton !== null"
                                                :class="act.danger ? 'text-destructive hover:bg-destructive/10 hover:text-destructive' : ''"
                                                @click="handleRowAction(field, row, ai)"
                                            >{{ act.label }}</Button>
                                        </td>
                                    </tr>
                                    <tr v-if="!filteredRows(field).length">
                                        <td
                                            :colspan="(field.columns?.length || 1) + (isSelectable(field) ? 1 : 0) + (field.rowActions?.length ? 1 : 0)"
                                            class="px-3 py-8 text-center text-muted-foreground"
                                        >{{ field.emptyText || 'Нічого не знайдено' }}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <div
                            v-if="isSelectable(field) && field.multiple !== false"
                            class="border-t border-border bg-muted/30 px-3 py-1.5 text-muted-foreground"
                        >Вибрано: {{ selectedCount(field) }}</div>
                    </div>
                </template>
                <template v-else-if="field.fieldtype === 'Check'">
                    <div class="flex items-center space-x-2 py-1">
                        <Checkbox :id="field.fieldname" v-model="formValues[field.fieldname]" />
                        <label :for="field.fieldname" class="cursor-pointer">{{ field.label }}</label>
                    </div>
                </template>
                <template v-else-if="field.fieldtype === 'LongText' || field.fieldtype === 'Code'">
                    <div class="flex items-center justify-between gap-2">
                        <label :for="field.fieldname" class="font-medium text-foreground">{{ field.label }}</label>
                        <button
                            v-if="field.read_only"
                            type="button"
                            class="shrink-0 px-2 py-0.5 rounded border border-border text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
                            @click="copyToClipboard(field.fieldname, String(formValues[field.fieldname] ?? ''))"
                        >
                            {{ copiedField === field.fieldname ? 'Скопійовано ✓' : 'Копіювати' }}
                        </button>
                    </div>
                    <p v-if="field.description" class="text-muted-foreground -mt-1">{{ field.description }}</p>
                    <textarea
                        :id="field.fieldname"
                        v-model="formValues[field.fieldname]"
                        :readonly="field.read_only"
                        rows="12"
                        :class="[
                            'w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none',
                            field.fieldtype === 'Code' ? 'font-mono' : '',
                            field.read_only ? 'bg-muted/40 cursor-default' : '',
                        ]"
                    />
                </template>
                <template v-else-if="field.fieldtype === 'Password'">
                    <label :for="field.fieldname" class="font-medium text-foreground">{{ field.label }}</label>
                    <p v-if="field.description" class="text-muted-foreground -mt-1">{{ field.description }}</p>
                    <PasswordField
                        :field="{
                            fieldname: field.fieldname,
                            fieldtype: 'Password',
                            label: field.label,
                            placeholder: field.placeholder,
                            required: field.required,
                            read_only: field.read_only,
                            show_strength: field.show_strength,
                        }"
                        :model-value="formValues[field.fieldname]"
                        @update:model-value="formValues[field.fieldname] = $event"
                    />
                </template>
                <template v-else-if="field.fieldtype === 'Link'">
                    <label :for="field.fieldname" class="font-medium text-foreground">{{ field.label }}</label>
                    <p v-if="field.description" class="text-muted-foreground -mt-1">{{ field.description }}</p>
                    <LinkField
                        :field="{ fieldname: field.fieldname, fieldtype: 'Link', options: field.options, label: field.label }"
                        :model-value="formValues[field.fieldname]"
                        @update:model-value="formValues[field.fieldname] = $event"
                        @create-new="() => {}"
                    />
                </template>
                <template v-else>
                    <label :for="field.fieldname" class="font-medium text-foreground">{{ field.label }}</label>
                    <p v-if="field.description" class="text-muted-foreground -mt-1">{{ field.description }}</p>
                    <Input :id="field.fieldname" v-model="formValues[field.fieldname]" :placeholder="field.placeholder"
                        :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
                        class="w-full"
                        @keydown.enter="onConfirm" />
                </template>
            </div>
        </div>

        <!-- Progress -->
        <div v-else-if="state.type === 'progress'" class="space-y-2 py-2">
            <div class="w-full h-2.5 bg-muted rounded-full overflow-hidden">
                <div class="h-full bg-primary rounded-full transition-all duration-300"
                    :style="{ width: `${state.progress.percent}%` }" />
            </div>
            <div class="flex items-center justify-between text-muted-foreground">
                <span v-if="state.progress.description">{{ state.progress.description }}</span>
                <span class="tabular-nums ml-auto">{{ state.progress.percent }}%</span>
            </div>
        </div>
    </div>

    <!-- Unified Footer -->
    <DialogFooter
      v-if="state.type !== 'progress'"
      :class="state.type === 'dialog' && state.buttons.length ? 'sm:flex-wrap' : ''"
    >
        <template v-if="state.type === 'msgprint'">
            <Button @click="close()">OK</Button>
        </template>
        <template v-else-if="state.type === 'confirm'">
            <Button variant="outline" @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">Підтвердити</Button>
        </template>
        <template v-else-if="state.type === 'prompt'">
            <Button variant="outline" @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">OK</Button>
        </template>
        <template v-else-if="state.type === 'dialog' && state.buttons.length">
            <Button
                v-for="(btn, i) in state.buttons"
                :key="i"
                :variant="btn.variant ?? 'outline'"
                :disabled="state.busyButton !== null"
                @click="handleAction(i)"
            >
                <Spinner v-if="state.busyButton === i" class="size-4 mr-2" />
                {{ btn.label }}
            </Button>
            <Button variant="ghost" :disabled="state.busyButton !== null" @click="onCancel">Закрити</Button>
        </template>
        <template v-else-if="state.type === 'dialog'">
            <Button variant="outline" @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">{{ state.primaryLabel }}</Button>
        </template>
    </DialogFooter>

    <!-- In-dialog confirm overlay (ctx.confirm from an action button) -->
    <div v-if="state.actionConfirm"
        class="absolute inset-0 z-20 flex items-center justify-center rounded-lg bg-background/70 backdrop-blur-[2px] p-6">
        <div class="w-full max-w-xs rounded-lg border bg-card p-4 shadow-lg flex flex-col gap-3">
            <p class="text-foreground leading-relaxed">{{ state.actionConfirm.message }}</p>
            <div class="flex justify-end gap-2">
                <Button variant="outline" size="sm" @click="resolveActionConfirm(false)">Скасувати</Button>
                <Button variant="destructive" size="sm" @click="resolveActionConfirm(true)">Підтвердити</Button>
            </div>
        </div>
    </div>
    </DialogContent>
  </Dialog>
</template>
