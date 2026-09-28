<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType, DocField } from '@/types'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { filterFieldsByName } from '@/core/fieldFilter'
import { ExternalLink } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { docUrl } from '@/core/workspaceUrl'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const props = defineProps<{
  dt: DocType
  /** Initial field values (e.g. typed text from Link field) */
  preset?: Record<string, unknown>
  workspace?: string
  /**
   * 'link' — after save, emit 'saved' with the doc name and close.
   * 'list' — show two buttons: "Save and close" / "Save and open".
   */
  mode: 'link' | 'list'
}>()

const emit = defineEmits<{
  close: []
  /** Emitted after a successful save, with the saved document's name field */
  saved: [docname: string]
}>()

const { t } = useI18n()
const router = useRouter()
const toast = useToast()
const queryClient = useQueryClient()

const { form, isSaving, save } = useDocument(props.dt.name, null)
const validationErrors = ref<Record<string, string>>({})

onMounted(() => {
  if (props.preset) Object.assign(form.value, props.preset)
})

// ── Field filtering ───────────────────────────────────────────────────────────
const LAYOUT_TYPES = getLayoutTypeSet()

function filterForQuickEntry(fields: DocField[]): DocField[] {
  const visible = new Set(
    fields
      .filter(f => !LAYOUT_TYPES.has(f.fieldtype) && (f.required || f.in_quick_entry))
      .map(f => f.fieldname),
  )

  if (visible.size === 0) {
    fields.filter(f => f.required).forEach(f => visible.add(f.fieldname))
  }

  return filterFieldsByName(fields, visible)
}

const filteredDt = computed<DocType>(() => ({
  ...props.dt,
  fields: filterForQuickEntry(props.dt.fields),
}))

// ── Save handlers ─────────────────────────────────────────────────────────────
async function handleSave(openAfter: boolean) {
  validationErrors.value = {}
  try {
    const saved = await save()
    const savedDoc = saved as { id: string; name: string }
    toast.success(t('Saved'))
    queryClient.invalidateQueries({ queryKey: ['documents', props.dt.name] })
    emit('saved', savedDoc.name)
    emit('close')
    if (openAfter) {
      router.push(docUrl(props.dt.name, savedDoc.id, props.workspace))
    }
  } catch (err: unknown) {
    const e = err as {
      response?: {
        status?: number
        data?: {
          detail?: string | string[]
          error?: { message?: string; details?: string[] }
        }
      }
    }
    const status = e?.response?.status
    const apiMessage = e?.response?.data?.error?.message
    const detailRaw = e?.response?.data?.detail

    if (status === 422) {
      const details: string[] = Array.isArray(detailRaw)
        ? detailRaw
        : typeof detailRaw === 'string' ? [detailRaw] : []
      if (details.length === 0 && apiMessage) details.push(apiMessage)
      let hasFieldErrors = false
      details.forEach((d: string) => {
        const match = d.match(/^([a-z_]+):\s*(.+)$/)
        if (match) { validationErrors.value[match[1]] = match[2]; hasFieldErrors = true }
      })
      toast.error(hasFieldErrors ? t('Check the form for errors') : details.join('; ') || t('Validation error'))
    } else if (apiMessage) {
      toast.error(apiMessage)
    } else if (typeof detailRaw === 'string' && detailRaw.trim()) {
      toast.error(detailRaw)
    } else {
      toast.error(t('Save error'))
    }
  }
}

function onFormUpdate(updated: Record<string, unknown>) {
  Object.assign(form.value, updated)
}

const isVisible = ref(true)
</script>

<template>
  <Dialog
    :open="isVisible"
    @update:open="(v: boolean) => { isVisible = v; if (!v) emit('close') }"
  >
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ t('New {doctype}').replace('{doctype}', dt.label) }}</DialogTitle>
        <DialogDescription>{{ t('Quick entry') }}</DialogDescription>
      </DialogHeader>

      <div class="-mx-6 max-h-[60vh] overflow-y-auto px-6">
        <FormRenderer
          :doctype="filteredDt"
          :model-value="form"
          :disabled="isSaving"
          :errors="validationErrors"
          @update:model-value="onFormUpdate"
        />
      </div>

      <DialogFooter>
        <Button variant="outline" :disabled="isSaving" @click="emit('close')">
          {{ t('Cancel') }}
        </Button>

        <template v-if="mode === 'list'">
          <Button variant="secondary" :disabled="isSaving" @click="handleSave(false)">
            {{ t('Save and close') }}
          </Button>
          <Button :disabled="isSaving" @click="handleSave(true)">
            <ExternalLink class="size-4" />
            {{ t('Save and open') }}
          </Button>
        </template>

        <Button v-else :disabled="isSaving" @click="handleSave(false)">
          {{ t('Save') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
