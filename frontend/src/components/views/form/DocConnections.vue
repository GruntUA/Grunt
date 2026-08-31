<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ChevronRight, Plus } from '@lucide/vue'

import client from '@/core/api/client'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { DocType, DocConnectionsResult } from '@/types'

const props = defineProps<{
  dt: DocType
  document: Record<string, any>
  workspace?: string
}>()

const emit = defineEmits<{
  'create-new': [doctype: string, preset: Record<string, unknown>, fieldname: string]
}>()

const result = ref<DocConnectionsResult | null>(null)
const loading = ref(false)

function docLinkValue(): string {
  const v = props.dt.is_tree ? props.document?.id : (props.document?.name ?? props.document?.id)
  return v ? String(v) : ''
}

async function load() {
  const id = docLinkValue()
  if (!id || !props.dt?.name) {
    result.value = null
    return
  }
  loading.value = true
  try {
    const { data } = await client.get(
      '/api/v1/method/grunt.document.connections.get_connections',
      { params: { doctype: props.dt.name, doc_id: props.document?.name ?? id } },
    )
    result.value = data?.data ?? null
  } catch {
    result.value = null
  } finally {
    loading.value = false
  }
}

watch(() => [props.dt?.name, props.document?.name], load, { immediate: true })

function listTo(link: { link_doctype: string; fieldname: string }) {
  return {
    name: 'workspace-list',
    params: { workspaceName: props.workspace || 'grunt', doctype: link.link_doctype },
    query: { [`filter[${link.fieldname}__eq]`]: docLinkValue() },
  }
}

function docTo(link_doctype: string, name: string) {
  return {
    name: 'workspace-form',
    params: { workspaceName: props.workspace || 'grunt', doctype: link_doctype, id: name },
  }
}

function handleAdd(link: { link_doctype: string; fieldname: string; via_child: boolean }) {
  const id = docLinkValue()
  if (!id || link.via_child) return // child-table links can't be prefilled generically
  emit('create-new', link.link_doctype, { [link.fieldname]: id }, '')
}

const hasAny = computed(() => (result.value?.groups ?? []).some((g) => g.links.length > 0))
</script>

<template>
  <div v-if="loading || hasAny" class="flex flex-col gap-3">
    <p v-if="loading" class="text-xs text-muted-foreground px-0.5">Завантаження зв'язків…</p>

    <div
      v-for="group in (hasAny ? (result?.groups ?? []) : [])"
      :key="group.name || '_'"
      class="flex flex-col gap-1.5"
    >
      <span
        v-if="group.name"
        class="text-xs font-semibold text-muted-foreground/80 uppercase tracking-wider px-0.5"
      >
        {{ group.name }}
      </span>

      <div class="flex flex-wrap gap-2">
        <Collapsible
          v-for="link in group.links"
          :key="link.link_doctype + link.fieldname"
          class="bg-background border border-border/80 rounded-lg overflow-hidden"
        >
          <div class="inline-flex items-center gap-2.5 px-3 py-1.5 group/link">
            <CollapsibleTrigger
              :disabled="!link.count"
              class="flex items-center gap-2.5 disabled:cursor-default"
            >
              <ChevronRight
                class="size-3 text-muted-foreground/50 transition-transform data-[disabled]:opacity-0 [[data-state=open]_&]:rotate-90"
              />
              <span
                class="text-xs font-semibold text-muted-foreground uppercase tracking-wider group-hover/link:text-primary transition-colors"
              >
                {{ link.label }}
              </span>
              <Badge
                variant="secondary"
                class="rounded-md font-mono text-xs h-4.5 px-1.5 min-w-[20px] flex items-center justify-center bg-muted/50 border-none"
              >
                {{ link.count }}
              </Badge>
            </CollapsibleTrigger>

            <button
              v-if="!link.via_child"
              type="button"
              class="size-5 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary flex items-center justify-center transition-colors border border-transparent hover:border-primary/20 -mr-1"
              :title="`Створити новий ${link.link_doctype}`"
              @click="handleAdd(link)"
            >
              <Plus class="size-3.5" />
            </button>
          </div>

          <CollapsibleContent>
            <div class="flex flex-col border-t border-border/60 bg-muted/20 px-1 py-1">
              <RouterLink
                v-for="row in link.preview"
                :key="row.name"
                :to="docTo(link.link_doctype, row.name)"
                class="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-background text-xs no-underline text-foreground"
              >
                <ChevronRight class="size-3 text-muted-foreground/40" />
                <span class="truncate">{{ row.title }}</span>
              </RouterLink>
              <RouterLink
                v-if="link.count > link.preview.length"
                :to="listTo(link)"
                class="px-2 py-1.5 text-xs text-primary hover:underline no-underline"
              >
                Переглянути всі {{ link.count }} →
              </RouterLink>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  </div>
</template>
