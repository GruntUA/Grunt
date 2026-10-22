<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, watch } from 'vue'
import type { Component } from 'vue'
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from '@lucide/vue'
import { useDialog, type DialogField } from '@/core/composables/useDialog'
import { getAsyncFieldComponent, getFieldDef, getStorageClass, isNumericType } from '@/core/fieldRegistry'
import { parseSelectOptions } from '@/lib/selectOptions'
import type { DocField } from '@/types'
import DialogTableField from './DialogTableField.vue'
import {
  AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Progress } from '@/components/ui/progress'
import { Button, type ButtonVariants } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()
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

const SIZE_CLASS = { small: 'sm:max-w-md', large: 'sm:max-w-lg', 'extra-large': 'sm:max-w-2xl' }

// HTML and Table are drawn here; every other type is the regular form field
// component, and one that renders its own label (manifest own_label) skips the dialog's.
function hasOwnLabel(f: DialogField): boolean {
  const type = f.fieldtype ?? 'Data'
  return type !== 'HTML' && type !== 'Table' && !!getFieldDef(type)?.own_label
}

const formValues = ref<Record<string, any>>({})

function emptyValue(f: DialogField): unknown {
  if (f.fieldtype === 'Table') return f.multiple === false ? null : []
  const type = f.fieldtype ?? 'Data'
  if (getStorageClass(type) === 'bool') return false
  if (isNumericType(type)) return null
  return ''
}

function reseedFormValues() {
  formValues.value = Object.fromEntries(state.fields.map(f => [f.fieldname, f.default ?? emptyValue(f)]))
}

watch(() => state.open, (v) => {
  if (v && state.type === 'dialog') reseedFormValues()
})

const copiedField = ref<string | null>(null)
let copiedTimer: ReturnType<typeof setTimeout> | undefined

async function copyToClipboard(fieldname: string) {
  try {
    await navigator.clipboard.writeText(String(formValues.value[fieldname] ?? ''))
  } catch {
    return // insecure context / denied - the text is still selectable in the field
  }
  copiedField.value = fieldname
  clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => { copiedField.value = null }, 2000)
}

function isCopyable(f: DialogField): boolean {
  return (f.fieldtype === 'LongText' || f.fieldtype === 'Code') && !!f.read_only
}

function askConfirm(message: string): Promise<boolean> {
  return new Promise<boolean>((res) => { state.actionConfirm = { message, resolve: res } })
}

function resolveActionConfirm(v: boolean) {
  const r = state.actionConfirm?.resolve
  state.actionConfirm = null
  r?.(v)
}

/** Runs an in-dialog handler, locking every button until it settles. */
async function runBusy(busyId: number, fn: () => unknown) {
  if (state.busyButton !== null) return
  state.busyButton = busyId
  try {
    await fn()
  } catch (e) {
    console.error('Dialog action failed', e)
  } finally {
    state.busyButton = null
  }
}

function handleRowAction(f: DialogField, row: Record<string, unknown>, idx: number) {
  const act = f.rowActions?.[idx]
  if (!act) return
  return runBusy(-1, () => act.onClick(row, {
    confirm: askConfirm,
    setRows: (rows) => { f.rows = rows },
  }))
}

function handleAction(idx: number) {
  const btn = state.buttons[idx]
  if (!btn) return
  return runBusy(idx, () => btn.action({
    values: { ...formValues.value },
    setField: (fieldname, patch) => {
      const f = state.fields.find(x => x.fieldname === fieldname)
      if (!f) return
      Object.assign(f, patch)
      // keep the live input value in sync when `default` is rewritten
      if ('default' in patch) formValues.value[fieldname] = patch.default
      if (patch.options !== undefined && f.fieldtype === 'Select'
        && !parseSelectOptions(patch.options).some(o => o.value === String(formValues.value[fieldname] ?? ''))) {
        formValues.value[fieldname] = ''
      }
    },
    setFields: (fields) => {
      state.fields = fields
      reseedFormValues()
    },
    confirm: askConfirm,
    close: (value?: unknown) => close(value),
  }))
}

const onConfirm = () => close(state.type === 'dialog' ? { ...formValues.value } : true)
const onCancel = () => close(state.type === 'confirm' ? false : undefined)

/** Enter in a plain text input submits; comboboxes, textareas and IME composition keep it. */
function onFieldsEnter(e: KeyboardEvent) {
  const el = e.target
  if (e.isComposing || !(el instanceof HTMLInputElement) || el.type === 'checkbox' || el.getAttribute('role') === 'combobox') return
  e.preventDefault()
  onConfirm()
}

interface FooterButton { label: string; variant: ButtonVariants['variant']; onClick: () => unknown; busy?: boolean }

const footerButtons = computed<FooterButton[]>(() => {
  if (state.type === 'msgprint') return [{ label: 'OK', variant: 'default', onClick: () => close() }]
  if (state.type !== 'dialog') return []
  if (!state.buttons.length) {
    return [
      { label: t('Cancel'), variant: 'outline', onClick: onCancel },
      { label: state.primaryLabel, variant: 'default', onClick: onConfirm },
    ]
  }
  return [
    ...state.buttons.map((b, i) => ({
      label: b.label, variant: b.variant ?? 'outline', onClick: () => handleAction(i), busy: state.busyButton === i,
    })),
    { label: t('Close'), variant: 'ghost', onClick: onCancel },
  ]
})
</script>

<template>
  <AlertDialog :open="state.open && state.type === 'confirm'" @update:open="(v: boolean) => { if (!v) onCancel() }">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ state.title }}</AlertDialogTitle>
        <AlertDialogDescription class="whitespace-pre-line">{{ state.message }}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>{{ t('Cancel') }}</AlertDialogCancel>
        <!-- Not AlertDialogAction: it closes the dialog itself first, and
             @update:open would resolve the confirm as cancelled. -->
        <Button :variant="state.destructive ? 'destructive' : 'default'" @click="onConfirm">
          {{ state.primaryLabel }}
        </Button>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>

  <Dialog :open="state.open && state.type !== 'confirm'" @update:open="(v: boolean) => { if (!v) onCancel() }">
    <DialogContent class="p-0 px-6 pb-4 pt-2" :class="SIZE_CLASS[state.size]">
      <DialogHeader v-if="state.title">
        <DialogTitle class="font-semibold flex items-center gap-2">
          <span v-if="state.indicator && !msgIndicator"
            class="inline-block w-2.5 h-2.5 rounded-full shrink-0"
            :style="{ backgroundColor: state.indicator }" />
          {{ state.title }}
        </DialogTitle>
      </DialogHeader>
      <DialogTitle v-else class="sr-only">{{ t('Dialog') }}</DialogTitle>
      <DialogDescription class="sr-only">{{ t('Dialog') }}</DialogDescription>

      <div v-if="state.type === 'msgprint'" class="flex gap-3 py-2">
        <component :is="msgIndicator.icon" v-if="msgIndicator" class="size-5 shrink-0 mt-px" :class="msgIndicator.class" />
        <div class="text-foreground/85 leading-relaxed whitespace-pre-wrap [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2"
          v-html="state.message" />
      </div>

      <!-- form() / prompt() / select() -->
      <FieldGroup v-else-if="state.type === 'dialog'" class="py-2" @keydown.enter="onFieldsEnter">
        <Field v-for="field in state.fields" :key="field.fieldname">
          <template v-if="!hasOwnLabel(field)">
            <div v-if="isCopyable(field)" class="flex items-center justify-between gap-2">
              <FieldLabel>{{ field.label }}</FieldLabel>
              <Button variant="outline" size="xs" @click="copyToClipboard(field.fieldname)">
                {{ copiedField === field.fieldname ? t('Copied') + ' ✓' : t('Copy') }}
              </Button>
            </div>
            <FieldLabel v-else-if="field.label">{{ field.label }}</FieldLabel>
            <FieldDescription v-if="field.description">{{ field.description }}</FieldDescription>
          </template>

          <!-- HTML content comes from `default` (rewritable via setField); `plain` drops the QR-style frame -->
          <template v-if="field.fieldtype === 'HTML'">
            <div v-if="field.plain" v-html="String(field.default || '')"
              class="text-foreground/85 leading-relaxed [&_a]:text-primary [&_a]:underline" />
            <div v-else v-html="String(field.default || '').replace(/<\?xml.*\?>/g, '')"
              class="rounded-lg border-2 border-dashed p-6 flex justify-center bg-muted shadow-inner min-h-[240px] items-center [&>svg]:block [&>svg]:max-w-full [&>svg]:h-auto" />
          </template>
          <DialogTableField
            v-else-if="field.fieldtype === 'Table'"
            v-model="formValues[field.fieldname]"
            :field="field"
            :busy="state.busyButton !== null"
            @row-action="(row, i) => handleRowAction(field, row, i)"
          />
          <component
            :is="getAsyncFieldComponent(field.fieldtype ?? 'Data')"
            v-else
            v-model="formValues[field.fieldname]"
            :field="field as DocField"
          />
        </Field>
      </FieldGroup>

      <div v-else-if="state.type === 'progress'" class="space-y-2 py-2">
        <Progress :model-value="state.progress.percent" />
        <div class="flex items-center justify-between text-muted-foreground">
          <span v-if="state.progress.description">{{ state.progress.description }}</span>
          <span class="tabular-nums ml-auto">{{ state.progress.percent }}%</span>
        </div>
      </div>

      <DialogFooter v-if="footerButtons.length" class="sm:flex-wrap">
        <Button
          v-for="(btn, i) in footerButtons"
          :key="i"
          :variant="btn.variant"
          :disabled="state.busyButton !== null"
          @click="btn.onClick"
        >
          <Spinner v-if="btn.busy" class="size-4 mr-2" />
          {{ btn.label }}
        </Button>
      </DialogFooter>

      <!-- ctx.confirm from an action button, stacked over this dialog -->
      <AlertDialog :open="!!state.actionConfirm" @update:open="(v: boolean) => { if (!v) resolveActionConfirm(false) }">
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{{ t('Confirmation') }}</AlertDialogTitle>
            <AlertDialogDescription>{{ state.actionConfirm?.message }}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{{ t('Cancel') }}</AlertDialogCancel>
            <Button variant="destructive" @click="resolveActionConfirm(true)">{{ t('Confirm') }}</Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DialogContent>
  </Dialog>
</template>
