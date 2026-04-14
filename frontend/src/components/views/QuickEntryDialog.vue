<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType, DocField } from '@/types'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import { Button } from '@/components/ui/button'
import { X, ExternalLink } from 'lucide-vue-next'

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

const LAYOUT_TYPES = new Set(['Section', 'Column', 'Tab'])

/**
 * Return a filtered field list suitable for the Quick Entry dialog.
 *
 * Data fields are included when: field.reqd || field.in_quick_entry.
 * Layout fields (Section/Column/Tab) are included only when they contain
 * at least one included data field within their scope.
 */
function filterForQuickEntry(fields: DocField[]): DocField[] {
  const visible = new Set(
    fields
      .filter(f => !LAYOUT_TYPES.has(f.fieldtype) && (f.required || f.in_quick_entry))
      .map(f => f.fieldname),
  )

  // Fallback: if nothing is marked, show all required fields
  if (visible.size === 0) {
    fields.filter(f => f.required).forEach(f => visible.add(f.fieldname))
  }

  // Does the range [start, end) contain any visible data field?
  function hasVisibleIn(start: number, end: number): boolean {
    for (let i = start; i < end; i++) {
      if (!LAYOUT_TYPES.has(fields[i].fieldtype) && visible.has(fields[i].fieldname)) return true
    }
    return false
  }

  // Find the index where the scope of a layout field at position i ends.
  // A Tab's scope ends at the next Tab.
  // A Section's scope ends at the next Section or Tab.
  // A Column's scope ends at the next Column, Section, or Tab.
  function scopeEnd(i: number, type: string): number {
    for (let j = i + 1; j < fields.length; j++) {
      if (fields[j].fieldtype === type) return j
      if (type !== 'Tab' && fields[j].fieldtype === 'Tab') return j
      if (type === 'Column' && fields[j].fieldtype === 'Section') return j
    }
    return fields.length
  }

  const result: DocField[] = []
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i]
    if (LAYOUT_TYPES.has(f.fieldtype)) {
      if (hasVisibleIn(i + 1, scopeEnd(i, f.fieldtype))) result.push(f)
    } else if (visible.has(f.fieldname)) {
      result.push(f)
    }
  }
  return result
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
      const ws = props.workspace ?? 'grunt'
      router.push(`/${ws}/list/${props.dt.name}/${savedDoc.id}`)
    }
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { detail?: string | string[] } } }
    if (e?.response?.status === 422) {
      const detail = e.response?.data?.detail
      const details: string[] = Array.isArray(detail)
        ? detail
        : typeof detail === 'string' ? [detail] : []
      let hasFieldErrors = false
      details.forEach((d: string) => {
        const match = d.match(/^([a-z_]+):\s*(.+)$/)
        if (match) { validationErrors.value[match[1]] = match[2]; hasFieldErrors = true }
      })
      toast.error(hasFieldErrors ? t('Check the form for errors') : details.join('; ') || t('Validation error'))
    } else {
      toast.error(t('Save error'))
    }
  }
}

function onFormUpdate(updated: Record<string, unknown>) {
  Object.assign(form.value, updated)
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <!-- Overlay -->
      <div
        class="absolute inset-0 bg-black/60 backdrop-blur-sm"
        @click="emit('close')"
      />

      <!-- Dialog panel -->
      <div class="relative z-10 flex flex-col bg-background border border-border rounded-xl shadow-2xl w-[90vw] max-w-4xl max-h-[90vh]">
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
          <h2 class="text-lg font-semibold text-foreground">
            {{ t('New {doctype}', { doctype: dt.label }) }}
          </h2>
          <button
            type="button"
            class="text-muted-foreground hover:text-foreground transition-colors rounded-md p-1"
            @click="emit('close')"
          >
            <X class="size-5" />
          </button>
        </div>

        <!-- Scrollable body -->
        <div class="flex-1 overflow-y-auto p-6">
          <FormRenderer
            :doctype="filteredDt"
            :model-value="form"
            :disabled="isSaving"
            :errors="validationErrors"
            @update:model-value="onFormUpdate"
          />
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-border flex-shrink-0 bg-muted/30 rounded-b-xl">
          <Button variant="ghost" :disabled="isSaving" @click="emit('close')">
            {{ t('Cancel') }}
          </Button>

          <!-- List mode: two action buttons -->
          <template v-if="mode === 'list'">
            <Button variant="outline" :disabled="isSaving" @click="handleSave(false)">
              {{ t('Save and close') }}
            </Button>
            <Button :disabled="isSaving" @click="handleSave(true)">
              <ExternalLink class="size-4 mr-1.5" />
              {{ t('Save and open') }}
            </Button>
          </template>

          <!-- Link mode: single save button -->
          <Button v-else :disabled="isSaving" @click="handleSave(false)">
            {{ t('Save') }}
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
