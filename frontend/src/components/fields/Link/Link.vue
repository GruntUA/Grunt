<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { ComboboxInput } from 'reka-ui'
import type { DocField } from '@/types'
import { ArrowUpRight, Plus, X } from '@lucide/vue'
import {
  Combobox, ComboboxAnchor, ComboboxGroup, ComboboxItem, ComboboxList, ComboboxSeparator,
} from '@/components/ui/combobox'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { TreeSelect } from '@/components/ui/tree-select'
import { cn } from '@/lib/utils'
import { useLinkField } from '@/core/composables/useLinkField'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  /** Current document values - used to evaluate link_filters with "eval:" prefix. */
  doc?: Record<string, unknown>
  /**
   * Flush "grid cell" look for use inside the inline child table - a
   * borderless, transparent input the height of a table row, matching the
   * other inline cell editors instead of a standalone bordered search box.
   */
  cell?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string]
}>()

// Value of the "Create …" row; picking it runs createNew instead of selecting.
const CREATE = '__create__'

// Handled on the item's own select event, before the combobox closes and
// restores the input to the picked record's label.
function onCreate(event: Event) {
  event.preventDefault()
  createNew()
}

const {
  t,
  query,
  results,
  isOpen,
  isLoading,
  isTree,
  treeNodes,
  treeLoading,
  canCreate,
  isSelected,
  activeFilterChips,
  linkedDocUrl,
  onTreeSelect,
  onInput,
  onOpenChange,
  select,
  clear,
  createNew,
  highlight,
  openLinkedDoc,
} = useLinkField(props, emit)

function onPick(value: unknown) {
  if (value != null && value !== CREATE) select(String(value))
}
</script>

<template>
  <!-- Tree mode -->
  <TreeSelect
    v-if="isTree"
    :model-value="(modelValue as string) || null"
    :options="treeNodes"
    :loading="treeLoading"
    :disabled="disabled || field.read_only"
    :placeholder="field.placeholder ?? t('Select {doctype}…', { doctype: field.options ?? '' })"
    :class="cn('w-full', error && 'border-destructive')"
    @update:model-value="onTreeSelect"
  >
    <template v-if="isSelected && linkedDocUrl" #actions>
      <RouterLink
        :to="linkedDocUrl"
        class="text-muted-foreground hover:text-primary transition-colors"
        :title="t('Open {doctype}', { doctype: field.options ?? '' })"
        @click.stop
        @mousedown.stop
      >
        <ArrowUpRight class="size-3.5" />
      </RouterLink>
    </template>
  </TreeSelect>

  <!-- Regular mode: type to search on the server, so the combobox doesn't filter itself -->
  <Combobox
    v-else
    :model-value="(modelValue as string) || undefined"
    :open="isOpen"
    :disabled="disabled || field.read_only"
    ignore-filter
    open-on-focus
    open-on-click
    :reset-search-term-on-blur="false"
    :reset-search-term-on-select="false"
    @update:open="onOpenChange"
    @update:model-value="onPick"
  >
    <ComboboxAnchor as-child class="w-full">
      <InputGroup
        :class="cell && 'h-8 rounded-none border-transparent border-b-border/30 bg-transparent shadow-none hover:border-input dark:bg-transparent has-[[data-slot=input-group-control]:focus-visible]:ring-0'"
      >
        <ComboboxInput as-child :model-value="query" :display-value="() => query" @update:model-value="onInput">
          <InputGroupInput
            :model-value="query"
            :placeholder="field.placeholder ?? t('Search {doctype}…', { doctype: field.options ?? '' })"
            :aria-label="field.label"
            :aria-invalid="error ? true : undefined"
            autocomplete="off"
            :data-preview-doctype="isSelected && field.options ? field.options : undefined"
            :data-preview-name="isSelected ? String(modelValue) : undefined"
          />
        </ComboboxInput>
        <InputGroupAddon align="inline-end">
          <Spinner v-if="isLoading" class="text-muted-foreground" />
          <template v-else-if="isSelected">
            <InputGroupButton
              v-if="linkedDocUrl"
              type="button"
              size="icon-xs"
              :title="t('Open {doctype}', { doctype: field.options ?? '' })"
              :aria-label="t('Open {doctype}', { doctype: field.options ?? '' })"
              @mousedown.prevent="openLinkedDoc"
            >
              <ArrowUpRight />
            </InputGroupButton>
            <InputGroupButton
              v-if="!disabled && !field.read_only"
              type="button"
              size="icon-xs"
              :title="t('Clear')"
              :aria-label="t('Clear')"
              @mousedown.prevent="clear"
            >
              <X />
            </InputGroupButton>
          </template>
        </InputGroupAddon>
      </InputGroup>
    </ComboboxAnchor>

    <ComboboxList
      class="w-(--reka-popper-anchor-width) min-w-56 p-0"
      align="start"
      data-link-dropdown
      @open-auto-focus.prevent
    >
      <ComboboxGroup v-if="results.length" class="max-h-52 overflow-y-auto p-1">
        <ComboboxItem v-for="item in results" :key="item.id" :value="item.name">
          <div class="flex min-w-0 flex-col gap-0.5">
            <span v-html="highlight(item.title)" />
            <span v-if="item.fields?.length" class="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
              <span v-for="f in item.fields" :key="f.fieldname">
                <span class="opacity-60">{{ f.label }}:</span>
                <span class="ml-1" v-html="highlight(f.value)" />
              </span>
            </span>
            <span v-else-if="item.subtitle" class="text-xs text-muted-foreground" v-html="highlight(item.subtitle)" />
          </div>
        </ComboboxItem>
      </ComboboxGroup>
      <div v-else class="py-6 text-center text-sm text-muted-foreground">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">{{ t('Nothing found for “{query}”', { query }) }}</span>
        <span v-else>{{ t('No records') }}</span>
      </div>

      <template v-if="canCreate">
        <ComboboxSeparator />
        <ComboboxGroup class="p-1">
          <ComboboxItem :value="CREATE" @select="onCreate">
            <Plus />
            <span v-if="query">
              {{ t('Create') }} <strong>{{ query }}</strong>
              <span class="ml-1 text-xs text-muted-foreground">({{ field.options }})</span>
            </span>
            <span v-else class="text-muted-foreground">{{ t('Create new') }} {{ field.options }}</span>
          </ComboboxItem>
        </ComboboxGroup>
      </template>

      <template v-if="activeFilterChips.length">
        <ComboboxSeparator />
        <div class="flex flex-wrap items-center gap-1.5 px-3 py-1.5 text-xs">
          <span class="text-muted-foreground">{{ t('Filter:') }}</span>
          <Badge v-for="chip in activeFilterChips" :key="chip.key" variant="secondary">{{ chip.display }}</Badge>
        </div>
      </template>
    </ComboboxList>
  </Combobox>
</template>
