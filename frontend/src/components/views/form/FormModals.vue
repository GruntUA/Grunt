<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import LinkField from '@/components/fields/Link/Link.vue'
import { docsApi, type DeleteImpact } from '@/core/api/docs'
import type { DocField } from '@/types'

const props = defineProps<{
  showDelete: boolean
  showLeave: boolean
  doctype?: string
  docId?: string | null
}>()

const { t } = useI18n()

const emit = defineEmits<{
  (e: 'update:showDelete', val: boolean): void
  (e: 'update:showLeave', val: boolean): void
  (e: 'confirmDelete', replaceWith?: string): void
  (e: 'confirmLeave'): void
  (e: 'cancelLeave'): void
}>()

const impact = ref<DeleteImpact | null>(null)
const impactLoading = ref(false)
const replaceWith = ref<string>('')
const ackDangling = ref(false)

watch(
  () => props.showDelete,
  async (open) => {
    if (!open) {
      impact.value = null
      replaceWith.value = ''
      ackDangling.value = false
      return
    }
    if (!props.doctype || !props.docId) return
    impactLoading.value = true
    try {
      impact.value = await docsApi.getDeleteImpact(props.doctype, [props.docId])
    } catch {
      impact.value = null
    } finally {
      impactLoading.value = false
    }
  },
)

const hasRefs = computed(() => (impact.value?.total ?? 0) > 0)

const replaceField = computed<DocField>(() => ({
  fieldname: 'replace_with',
  fieldtype: 'Link',
  label: '',
  options: props.doctype ?? '',
} as DocField))

const replaceIsSelf = computed(() => !!replaceWith.value && replaceWith.value === props.docId)
const canReassign = computed(() => !!replaceWith.value && !replaceIsSelf.value)
const canDelete = computed(() => canReassign.value || !hasRefs.value || ackDangling.value)

function groupLine(g: DeleteImpact['groups'][number]): string {
  const parts = [g.label]
  if (g.field_label) parts.push(g.field_label)
  if (g.in_child && g.parent_doctype) parts.push(t('in {doctype}').replace('{doctype}', g.parent_doctype))
  return parts.join(' · ')
}

function confirm() {
  emit('confirmDelete', canReassign.value ? replaceWith.value : undefined)
}
</script>

<template>
  <div>
    <!-- Delete confirmation -->
    <Dialog :open="showDelete" @update:open="emit('update:showDelete', $event)">
      <DialogContent class="w-[440px]" :show-close-button="false">
        <DialogHeader>
          <DialogTitle class="text-base">{{ t('Delete document?') }}</DialogTitle>
        </DialogHeader>

        <div v-if="impactLoading" class="flex items-center gap-2 text-muted-foreground py-2">
          <Loader2 class="size-4 animate-spin" />
          {{ t('Checking links…') }}
        </div>

        <template v-else-if="hasRefs">
          <p class="text-muted-foreground">
            {{ t('Other records link to this document') }}
            (<span class="font-semibold text-foreground">{{ impact!.total }}</span>).
            {{ t('Choose a replacement or delete without one.') }}
          </p>

          <ul class="my-1 max-h-40 overflow-y-auto rounded-md border border-border/60 bg-muted/30 divide-y divide-border/50">
            <li v-for="g in impact!.groups" :key="`${g.doctype}-${g.field}`"
              class="flex items-center justify-between gap-3 px-3 py-1.5">
              <span class="truncate">{{ groupLine(g) }}</span>
              <span class="shrink-0 tabular-nums font-semibold text-muted-foreground">{{ g.count }}</span>
            </li>
          </ul>

          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Replace with') }}</label>
            <LinkField
              :field="replaceField"
              :model-value="replaceWith"
              @update:model-value="replaceWith = ($event as string) ?? ''"
            />
            <p v-if="replaceIsSelf" class="text-destructive">
              {{ t('Cannot replace with the document being deleted.') }}
            </p>
          </div>

          <label v-if="!canReassign" class="flex items-start gap-2 cursor-pointer">
            <Checkbox
              :model-value="ackDangling"
              class="mt-0.5"
              @update:model-value="ackDangling = $event === true"
            />
            <span class="text-muted-foreground">
              {{ t('Delete without replacement — {n} links will become invalid.').replace('{n}', String(impact!.total)) }}
            </span>
          </label>
        </template>

        <p v-else class="text-muted-foreground">
          {{ t('This cannot be undone. All related data will be deleted permanently.') }}
        </p>

        <DialogFooter>
          <Button variant="ghost" @click="emit('update:showDelete', false)">{{ t('Cancel') }}</Button>
          <Button variant="destructive" :disabled="!canDelete" @click="confirm">
            {{ canReassign ? t('Delete and reassign') : t('Delete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Unsaved leave confirmation -->
    <Dialog :open="showLeave" @update:open="emit('update:showLeave', $event)">
      <DialogContent class="w-[400px]" :show-close-button="false">
        <DialogHeader>
          <DialogTitle class="text-base">{{ t('Unsaved changes') }}</DialogTitle>
        </DialogHeader>
        <p class="text-muted-foreground">{{ t('You have changes that will be lost if you leave this page. Leave without saving?') }}</p>
        <DialogFooter>
          <Button variant="ghost" @click="emit('cancelLeave')">{{ t('Stay') }}</Button>
          <Button variant="destructive" @click="emit('confirmLeave')">{{ t('Leave') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
