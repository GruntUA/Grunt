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
import { ExternalLink, Plus } from '@lucide/vue'

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

  function hasVisibleIn(start: number, end: number): boolean {
    for (let i = start; i < end; i++) {
      if (!LAYOUT_TYPES.has(fields[i].fieldtype) && visible.has(fields[i].fieldname)) return true
    }
    return false
  }

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
      router.push(`/${ws}/${props.dt.name}/${savedDoc.id}`)
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

const isVisible = ref(true)
</script>

<template>
  <Dialog 
    v-model:visible="isVisible" 
    modal 
    @hide="emit('close')"
    class="max-w-4xl w-[90vw]"
    :pt="{
        header: { class: 'px-8 py-4 border-b border-border/40' },
        content: { class: 'p-0' },
        footer: { class: 'px-8 py-3 border-t border-border/40 bg-muted/20 flex items-center' }
    }"
  >
    <template #header>
        <div class="flex items-center gap-3">
            <div class="size-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
                <Plus class="size-4 text-primary" />
            </div>
            <div class="flex flex-col">
                <span class="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 leading-none mb-0.5">Швидке додавання</span>
                <h2 class="text-base font-bold text-foreground tracking-tight">
                    Новий {{ dt.label }}
                </h2>
            </div>
        </div>
    </template>

    <div class="p-8 max-h-[60vh] overflow-y-auto custom-scrollbar">
      <FormRenderer
        :doctype="filteredDt"
        :model-value="form"
        :disabled="isSaving"
        :errors="validationErrors"
        @update:model-value="onFormUpdate"
      />
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-2 w-full">
          <Button text size="small" :disabled="isSaving" @click="emit('close')">
            {{ t('Cancel') }}
          </Button>

          <!-- List mode: two action buttons -->
          <template v-if="mode === 'list'">
            <Button outlined size="small" :disabled="isSaving" @click="handleSave(false)" class="font-medium">
              {{ t('Save and close') }}
            </Button>
            <Button size="small" :disabled="isSaving" @click="handleSave(true)" class="font-medium">
              <ExternalLink class="size-3.5 mr-1.5" />
              {{ t('Save and open') }}
            </Button>
          </template>

          <!-- Link mode: single save button -->
          <Button v-else size="small" :disabled="isSaving" @click="handleSave(false)" class="font-medium">
            {{ t('Save') }}
          </Button>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--p-content-border-color);
  border-radius: 10px;
}
</style>
