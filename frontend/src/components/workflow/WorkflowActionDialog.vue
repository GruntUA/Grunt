<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocType } from '@/types'
import type { WorkflowTransitionItem } from '@/core/api/docs'
import { filterFieldsByName } from '@/core/fieldFilter'
import FormRenderer from '@/core/renderer/FormRenderer.vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
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

// A `require_comment` transition's comment — the server adds it to the
// document's comments and the notification (values.__comment).
const comment = ref('')
const commentMissing = ref(false)

function onFormUpdate(updated: Record<string, unknown>) {
  Object.assign(form.value, updated)
}

function onSubmit() {
  // Only the declared prompt_fields go over the wire — the rest of `form`
  // exists purely so the layout's depends_on conditions resolve correctly.
  const values: Record<string, unknown> = Object.fromEntries(
    props.transition.prompt_fields.map(name => [name, form.value[name]]),
  )
  if (props.transition.require_comment) {
    commentMissing.value = !comment.value.trim()
    if (commentMissing.value) return
    values.__comment = comment.value.trim()
  }
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
          v-if="transition.prompt_fields.length"
          :doctype="promptDt"
          :model-value="form"
          :disabled="isSubmitting"
          :reqd-overrides="reqdOverrides"
          @update:model-value="onFormUpdate"
        />
        <div v-if="transition.require_comment" class="grid gap-2 py-2">
          <Label for="workflow-comment">{{ t('Comment') }} <span class="text-destructive">*</span></Label>
          <Textarea
            id="workflow-comment"
            v-model="comment"
            rows="4"
            :disabled="isSubmitting"
            @update:model-value="commentMissing = false"
          />
          <p v-if="commentMissing" class="text-destructive text-sm">{{ t('Add a comment') }}</p>
        </div>
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
