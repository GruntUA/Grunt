<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import draggable from 'vuedraggable'
import type { DocType, DocField } from '@/types'
import { docsApi } from '@/core/api/docs'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<{
  doctype: DocType
  columnField: string
}>()

const columnFieldDef = computed<DocField | undefined>(() =>
  props.doctype.fields.find(f => f.fieldname === props.columnField)
)

const columns = computed<string[]>(() => {
  if (!columnFieldDef.value?.options) return []
  return columnFieldDef.value.options.split('\n').map(s => s.trim()).filter(Boolean)
})

const cards = ref<Record<string, Record<string, unknown>[]>>({})
const isLoading = ref(true)

async function loadCards() {
  isLoading.value = true
  try {
    for (const col of columns.value) {
      const resp = await docsApi.list(props.doctype.name, {
        filters: { [props.columnField]: col },
        per_page: 100,
      })
      cards.value[col] = resp.data ?? []
    }
  } finally {
    isLoading.value = false
  }
}

interface DraggableChangeEvent {
  added?: { element: Record<string, unknown> }
  removed?: { element: Record<string, unknown> }
  moved?: { element: Record<string, unknown> }
}

function makeCardMovedHandler(col: string) {
  return async (evt: DraggableChangeEvent) => {
    if (!evt.added) return
    const card = evt.added.element
    await docsApi.update(props.doctype.name, String(card.id), { [props.columnField]: col })
  }
}

onMounted(loadCards)

const titleField = computed(() => props.doctype.title_field ?? 'name')
</script>

<template>
  <div class="flex gap-4 overflow-x-auto p-6 h-full">
    <div v-if="isLoading" class="flex items-center justify-center w-full">
      <Spinner size="lg" />
    </div>
    <template v-else>
      <div
        v-for="col in columns"
        :key="col"
        class="flex-shrink-0 w-72 flex flex-col"
      >
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-foreground">{{ col }}</h3>
          <span class="text-xs bg-background text-muted-foreground/70 rounded-full px-2 py-0.5">
            {{ (cards[col] ?? []).length }}
          </span>
        </div>
        <draggable
          v-model="cards[col]"
          group="kanban"
          item-key="id"
          class="flex flex-col gap-2 min-h-20 flex-1 bg-background rounded-lg p-2"
          @change="makeCardMovedHandler(col)"
        >
          <template #item="{ element: card }">
            <div
              class="bg-card border border-border rounded-md p-3 cursor-pointer hover:border-primary transition-colors shadow-sm"
            >
              <p class="text-sm font-medium text-foreground truncate">
                {{ (card[titleField] ?? card['name'] ?? card['id']) as string }}
              </p>
              <p class="text-xs text-muted-foreground/70 mt-1">
                {{ card['owner'] as string }}
              </p>
            </div>
          </template>
        </draggable>
      </div>
    </template>
  </div>
</template>
