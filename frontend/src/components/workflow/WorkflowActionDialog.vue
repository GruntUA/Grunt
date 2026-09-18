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

const form = ref<Record<string, unknown>>(
  Object.fromEntries(props.transition.prompt_fields.map(name => [name, props.doc[name] ?? null])),
)

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
        <Button :disabled="isSubmitting" @click="emit('submit', form)">
          {{ transition.action }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
