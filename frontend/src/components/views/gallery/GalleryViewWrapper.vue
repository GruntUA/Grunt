<script setup lang="ts">
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import BulkActionDialogs from '@/components/views/BulkActionDialogs.vue'
import GalleryView from './GalleryView.vue'

const props = defineProps<{
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  fields: DocField[]
  doctype: string
  imageField?: string
  workspace?: string
  isLoading?: boolean
  selectionCount: number
  selection: {
    selectedIds: string[]
    allSelected: boolean
    isSelected: (id: string) => boolean
    toggle: (id: string) => void
  }
  editableFields?: DocField[]
  meta?: { page: number; pages: number; total: number }
}>()

const emit = defineEmits<{
  delete: [replaceWith?: string]
  update: [field: string, value: unknown]
}>()
</script>

<template>
  <BulkActionDialogs
    :count="selectionCount"
    :total="meta?.total"
    :all-selected="selection.allSelected"
    :editable-fields="editableFields"
    :doctype="doctype"
    :selected-ids="selection.selectedIds"
    @delete="(rw) => emit('delete', rw)"
    @update="(field, value) => emit('update', field, value)"
  />
  <GalleryView
    :rows="rows"
    :columns="columns"
    :fields="fields"
    :doctype="doctype"
    :image-field="imageField"
    :workspace="workspace"
    :is-loading="isLoading"
    :selection="selection"
  />
</template>
