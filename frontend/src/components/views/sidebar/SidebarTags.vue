<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListboxContent, ListboxFilter, ListboxItem, ListboxRoot, useFilter } from 'reka-ui'
import type { DocSidebarState } from './useDocSidebar'
import { useToast } from '@/core/composables/useToast'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import {
  TagsInput,
  TagsInputInput,
  TagsInputItem,
  TagsInputItemDelete,
  TagsInputItemText,
} from '@/components/ui/tags-input'

const props = defineProps<{ sb: DocSidebarState }>()

const { t } = useI18n()
const toast = useToast()
const { contains } = useFilter({ sensitivity: 'base' })

const search = ref('')
const open = ref(false)
const known = ref<string[]>([])
let knownLoaded = false

// Tags are saved one by one, so the v-model is a view over the server bundle:
// setting it diffs against the bundle into add / remove calls.
const model = computed<string[]>({
  get: () => props.sb.bundle.value.tags.map((x) => x.tag),
  set: (next) => void sync(next),
})

async function sync(next: string[]) {
  const current = props.sb.bundle.value.tags
  const wanted = new Set(next.map((x) => x.trim().toLowerCase()))
  try {
    for (const tag of current) {
      if (!wanted.has(tag.tag.toLowerCase())) await props.sb.removeTag(tag.name)
    }
    for (const tag of next) {
      if (!current.some((x) => x.tag.toLowerCase() === tag.trim().toLowerCase())) await props.sb.addTag(tag)
    }
  } catch (e) {
    toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('Could not save the tag'))
  }
  search.value = ''
}

// Tags already used on this DocType, minus the applied ones.
const suggestions = computed(() => {
  const applied = new Set(model.value.map((x) => x.toLowerCase()))
  return known.value.filter((k) => !applied.has(k.toLowerCase()) && (!search.value || contains(k, search.value)))
})

async function onFocus() {
  if (!knownLoaded) {
    knownLoaded = true
    known.value = await props.sb.knownTags()
  }
  open.value = suggestions.value.length > 0
}

watch(search, (q) => {
  if (q) open.value = true
})
</script>

<template>
  <section class="flex flex-col gap-2">
    <h3 class="text-sm font-medium">{{ t('Tags') }}</h3>

    <Popover v-model:open="open">
      <ListboxRoot v-model="model" multiple highlight-on-hover>
        <PopoverAnchor as-child>
          <TagsInput v-model="model" delimiter="," add-on-paste class="w-full px-1.5">
            <TagsInputItem v-for="tag in model" :key="tag" :value="tag">
              <TagsInputItemText />
              <TagsInputItemDelete :aria-label="t('Remove tag {tag}', { tag })" />
            </TagsInputItem>

            <ListboxFilter v-model="search" as-child>
              <TagsInputInput
                :placeholder="model.length ? '' : t('Add tag…')"
                class="min-w-16"
                @focus="onFocus"
                @keydown.down="open = true"
              />
            </ListboxFilter>
          </TagsInput>
        </PopoverAnchor>

        <PopoverContent
          v-if="suggestions.length"
          align="start"
          class="w-(--reka-popper-anchor-width) p-1"
          @open-auto-focus.prevent
        >
          <ListboxContent class="max-h-56 overflow-y-auto" tabindex="0">
            <ListboxItem
              v-for="tag in suggestions"
              :key="tag"
              :value="tag"
              class="relative flex cursor-default items-center rounded-sm px-2 py-1.5 text-sm outline-hidden select-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
              @select="open = false"
            >
              {{ tag }}
            </ListboxItem>
          </ListboxContent>
        </PopoverContent>
      </ListboxRoot>
    </Popover>
  </section>
</template>
