<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocType } from '@/types'
import type { WorkflowTransitionItem } from '@/core/api/docs'
import { filterFieldsByName } from '@/core/fieldFilter'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const props = defineProps<{
  doctype: DocType
  transition: WorkflowTransitionItem
  /** Current document values, used to prefill the dialog's fields */
  doc: Record<string, unknown>
  isSubmitting?: boolean
  errorMessage?: string | null
}>()

const emit = defineEmits<{
  close: []
  submit: [values: Record<string, unknown>]
}>()

const { t } = useI18n()

// Seed with the full document, not just prompt_fields — the filtered layout
// can still include a Section/Column with a `depends_on` referencing other
// doc fields (e.g. `doc.status`), which must resolve correctly for the
// prompt fields inside it to actually render.
const form = ref<Record<string, unknown>>({ ...props.doc })

const promptDt = computed<DocType>(() => ({
  ...props.doctype,
  fields: filterFieldsByName(props.doctype.fields, new Set(props.transition.prompt_fields)),
}))

const reqdOverrides = computed(() =>
  Object.fromEntries(props.transition.prompt_fields.map(name => [name, true])),
)

function onFormUpdate(updated: Record<string, unknown>) {
  Object.assign(form.value, updated)
}

function onSubmit() {
  // Only the declared prompt_fields go over the wire — the rest of `form`
  // exists purely so the layout's depends_on conditions resolve correctly.
  const values = Object.fromEntries(props.transition.prompt_fields.map(name => [name, form.value[name]]))
  emit('submit', values)
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
        <DialogTitle>{{ transition.action }}</DialogTitle>
      </DialogHeader>

      <div class="-mx-6 max-h-[60vh] overflow-y-auto px-6">
        <FormRenderer
          :doctype="promptDt"
          :model-value="form"
          :disabled="isSubmitting"
          :reqd-overrides="reqdOverrides"
          @update:model-value="onFormUpdate"
        />
        <p v-if="errorMessage" class="text-destructive mt-2">{{ errorMessage }}</p>
      </div>

      <DialogFooter>
        <Button variant="outline" :disabled="isSubmitting" @click="emit('close')">
          {{ t('Cancel') }}
        </Button>
        <Button :disabled="isSubmitting" @click="onSubmit">
          {{ transition.action }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
