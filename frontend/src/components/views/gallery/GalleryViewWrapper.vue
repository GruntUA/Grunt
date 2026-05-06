<script setup lang="ts">
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import ListPagination from '@/components/views/ListPagination.vue'
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
  delete: []
  clear: []
  selectAll: []
  update: [field: string, value: string]
  'update:page': [page: number]
}>()
</script>

<template>
  <BulkActionBar
    :count="selectionCount"
    :total="meta?.total"
    :all-selected="selection.allSelected"
    :page-count="rows.length"
    :editable-fields="editableFields"
    @delete="emit('delete')"
    @clear="emit('clear')"
    @select-all="emit('selectAll')"
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
  <ListPagination
    v-if="meta"
    :page="meta.page"
    :pages="meta.pages"
    :total="meta.total"
    :per-page="20"
    @update:page="(p) => emit('update:page', p)"
  />
</template>
