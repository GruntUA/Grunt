<script setup lang="ts">
import { computed, useId } from 'vue'
import type { DocField } from '@/types'
import { Search, X, Loader2, Plus, ArrowUpRight } from '@lucide/vue'
import { TreeSelect } from '@/components/ui/tree-select'
import { cn } from '@/lib/utils'
import { useLinkField } from '@/core/composables/useLinkField'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  /** Current document values — used to evaluate link_filters with "eval:" prefix. */
  doc?: Record<string, unknown>
  /**
   * Flush "grid cell" look for use inside the inline child table — a
   * borderless, transparent input the height of a table row, matching the
   * other inline cell editors instead of a standalone bordered search box.
   */
  cell?: boolean
}>()

// Base classes for the regular-mode <input>; `pr-*` is appended in the template.
const inputClass = computed(() =>
  props.cell
    ? 'w-full h-8 rounded-none border border-transparent border-b-border/30 bg-transparent pl-8 text-xs text-foreground placeholder:text-muted-foreground shadow-none outline-none hover:border-input focus-visible:ring-0 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-60 transition-colors'
    : 'w-full rounded-md border border-input bg-transparent dark:bg-input/30 pl-8 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring disabled:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60 transition-colors',
)

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string]
}>()

// Stable ids to wire the combobox input to its teleported listbox for a11y.
const listboxId = useId()
const optionId = (i: number) => `${listboxId}-opt-${i}`

const linkField = useLinkField(props, emit)
const {
  t,
  query,
  results,
  isOpen,
  isLoading,
  activeIdx,
  dropdownStyle,
  isTree,
  treeNodes,
  treeLoading,
  canCreate,
  isSelected,
  activeFilterChips,
  linkedDocUrl,
  onTreeSelect,
  onInput,
  onFocus,
  onBlur,
  onKeydown,
  select,
  clear,
  createNew,
  highlight,
  openLinkedDoc,
} = linkField
</script>

<template>
  <!-- Tree mode -->
  <div v-if="isTree" class="relative flex items-center gap-1">
    <TreeSelect
      :model-value="(modelValue as string) || null"
      :options="treeNodes"
      :loading="treeLoading"
      :disabled="disabled || field.read_only"
      :placeholder="field.placeholder ?? t('Select {doctype}…', { doctype: field.options ?? '' })"
      :class="cn('w-full', error && 'border-destructive')"
      @update:model-value="onTreeSelect"
    />
    <button
      v-if="isSelected && linkedDocUrl"
      type="button"
      class="shrink-0 text-muted-foreground hover:text-primary transition-colors"
      :title="t('Open {doctype}', { doctype: field.options ?? '' })"
      @click="openLinkedDoc"
    >
      <ArrowUpRight class="size-4" />
    </button>
    <button
      v-if="isSelected && !disabled && !field.read_only"
      type="button"
      class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
      :title="t('Clear')"
      @click="clear"
    >
      <X class="size-4" />
    </button>
  </div>

  <!-- Regular mode: custom input + dropdown -->
  <div v-else :ref="(el) => { linkField.containerRef.value = el as HTMLElement | null }" class="relative">
    <div class="relative">
      <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />

      <input
        :value="query"
        :placeholder="field.placeholder ?? t('Search {doctype}…', { doctype: field.options ?? '' })"
        :disabled="disabled || field.read_only"
        :class="[
          inputClass,
          isSelected && linkedDocUrl ? 'pr-16' : 'pr-8',
          error ? 'border-destructive focus-visible:ring-destructive' : '',
        ]"
        autocomplete="off"
        role="combobox"
        aria-autocomplete="list"
        :aria-label="field.label"
        :aria-expanded="isOpen"
        :aria-controls="listboxId"
        :aria-activedescendant="isOpen && activeIdx >= 0 ? optionId(activeIdx) : undefined"
        :aria-invalid="error ? true : undefined"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />

      <div class="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1">
        <Loader2 v-if="isLoading" class="size-4 text-muted-foreground animate-spin" />
        <template v-else-if="isSelected">
          <button
            v-if="linkedDocUrl"
            type="button"
            class="text-muted-foreground hover:text-primary transition-colors"
            :title="t('Open {doctype}', { doctype: field.options ?? '' })"
            @mousedown.prevent="openLinkedDoc"
          >
            <ArrowUpRight class="size-4" />
          </button>
          <button
            v-if="!disabled && !field.read_only"
            type="button"
            class="text-muted-foreground hover:text-foreground transition-colors"
            :title="t('Clear')"
            :aria-label="t('Clear')"
            @mousedown.prevent="clear"
          >
            <X class="size-4" />
          </button>
        </template>
      </div>
    </div>

    <Teleport to="body">
    <div
      v-if="isOpen"
      :id="listboxId"
      data-link-dropdown
      role="listbox"
      :aria-label="field.label"
      :style="dropdownStyle"
      class="pointer-events-auto bg-popover border border-border rounded-lg shadow-md overflow-hidden"
    >
      <div v-if="results.length" class="max-h-52 overflow-y-auto py-1">
        <button
          v-for="(item, i) in results"
          :key="item.id"
          type="button"
          role="option"
          :id="optionId(i)"
          :aria-selected="i === activeIdx"
          :class="[
            'w-full text-left px-3 py-2 text-sm transition-colors flex flex-col gap-0.5',
            i === activeIdx ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
          ]"
          @mousedown.prevent="select(item)"
          @mouseover="activeIdx = i"
        >
          <span v-html="highlight(item.title)" />
          <span
            v-if="item.subtitle"
            class="text-xs text-muted-foreground"
            v-html="highlight(item.subtitle)"
          />
        </button>
      </div>

      <div v-else class="px-3 py-3 text-muted-foreground text-center">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">{{ t('Nothing found for “{query}”', { query }) }}</span>
        <span v-else>{{ t('No records') }}</span>
      </div>

      <template v-if="canCreate">
        <div class="border-t border-border" />
        <button
          type="button"
          role="option"
          :id="optionId(results.length)"
          :aria-selected="activeIdx === results.length"
          :class="[
            'w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors',
            activeIdx === results.length
              ? 'bg-accent text-accent-foreground'
              : 'text-primary hover:bg-accent/50',
          ]"
          @mousedown.prevent="createNew"
          @mouseover="activeIdx = results.length"
        >
          <Plus class="size-3.5 shrink-0" />
          <span v-if="query">
            {{ t('Create') }} <strong>{{ query }}</strong>
            <span class="text-muted-foreground text-xs ml-1">({{ field.options }})</span>
          </span>
          <span v-else class="text-muted-foreground">
            {{ t('Create new') }} {{ field.options }}
          </span>
        </button>
      </template>

      <template v-if="activeFilterChips.length">
        <div class="border-t border-border" />
        <div class="px-3 py-1.5 flex items-center gap-1.5 flex-wrap">
          <span class="text-xs text-muted-foreground">{{ t('Filter:') }}</span>
          <span
            v-for="chip in activeFilterChips"
            :key="chip.key"
            class="inline-flex items-center text-xs bg-primary/10 text-primary rounded px-1.5 py-0.5 font-medium"
          >
            {{ chip.display }}
          </span>
        </div>
      </template>
    </div>
    </Teleport>
  </div>
</template>
