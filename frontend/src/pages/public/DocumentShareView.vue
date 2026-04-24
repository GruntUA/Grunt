<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Loader2, AlertCircle, Sprout, Eye, Clock } from '@lucide/vue'

const route = useRoute()
const token = route.params.token as string

interface SharedField { fieldname: string; label: string; fieldtype: string }
interface SharedData {
  doctype: string
  doctype_label: string
  doc_id: string
  expires_at: string | null
  doc: Record<string, string | null>
  fields: SharedField[]
}

const data = ref<SharedData | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const resp = await fetch(`/api/v1/method/grunt.api.v1.share.get_shared_document?token=${encodeURIComponent(token)}`)
    if (resp.status === 410) { error.value = 'Термін дії посилання закінчився'; return }
    if (resp.status === 404) { error.value = 'Посилання не знайдено або деактивовано'; return }
    if (!resp.ok) { error.value = `Помилка ${resp.status}`; return }
    const json = await resp.json()
    data.value = json.data
  } catch (e) {
    error.value = 'Помилка мережі'
  } finally {
    loading.value = false
  }
})

const SKIP_FIELDS = new Set(['id', 'name', 'owner', 'created_at', 'modified_at', 'modified_by', 'docstatus'])
const MULTILINE = new Set(['LongText', 'Text', 'HTML'])

function formatVal(fieldtype: string, val: string | null): string {
  if (val === null || val === undefined || val === '') return '—'
  if (fieldtype === 'Check') return val === '1' || val === 'true' ? 'Так' : 'Ні'
  return val
}
</script>

<template>
  <div class="min-h-screen bg-muted/30">
    <!-- Minimal header -->
    <header class="bg-card border-b border-border/60 px-6 py-3 flex items-center gap-2.5">
      <div class="w-7 h-7 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
        <Sprout class="w-4 h-4" />
      </div>
      <span class="text-sm font-semibold text-foreground">Ґрунт</span>
      <span class="text-muted-foreground/40 text-xs ml-1">·</span>
      <span class="text-xs text-muted-foreground flex items-center gap-1">
        <Eye class="size-3" /> Перегляд документа
      </span>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center items-center py-32">
      <Loader2 class="size-8 animate-spin text-primary" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex flex-col items-center justify-center py-32 gap-4">
      <div class="size-16 rounded-full bg-destructive/10 flex items-center justify-center">
        <AlertCircle class="size-8 text-destructive" />
      </div>
      <p class="text-lg font-semibold text-foreground">{{ error }}</p>
      <p class="text-sm text-muted-foreground">Зверніться до власника документа за новим посиланням.</p>
    </div>

    <!-- Document -->
    <div v-else-if="data" class="max-w-3xl mx-auto py-10 px-4">
      <!-- Doc header -->
      <div class="bg-card border border-border rounded-xl shadow-sm px-6 py-5 mb-6">
        <p class="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">{{ data.doctype_label }}</p>
        <h1 class="text-2xl font-bold text-foreground">{{ data.doc['name'] ?? data.doc_id }}</h1>
        <div v-if="data.expires_at" class="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
          <Clock class="size-3" />
          Дійсно до {{ new Date(data.expires_at).toLocaleString('uk-UA') }}
        </div>
      </div>

      <!-- Fields -->
      <div class="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        <div class="px-6 py-4 border-b border-border/60">
          <h2 class="text-sm font-semibold text-foreground">Дані документа</h2>
        </div>
        <div class="divide-y divide-border/50">
          <div
            v-for="field in data.fields.filter(f => !SKIP_FIELDS.has(f.fieldname))"
            :key="field.fieldname"
            class="grid grid-cols-[180px_1fr] gap-4 px-6 py-3.5 hover:bg-muted/20 transition-colors"
          >
            <span class="text-sm text-muted-foreground font-medium truncate self-start pt-0.5">{{ field.label }}</span>
            <span
              :class="['text-sm text-foreground', MULTILINE.has(field.fieldtype) ? 'whitespace-pre-wrap' : '']"
            >{{ formatVal(field.fieldtype, data.doc[field.fieldname] ?? null) }}</span>
          </div>
        </div>
      </div>

      <!-- Footer note -->
      <p class="text-center text-xs text-muted-foreground mt-6">
        Цей документ надано у режимі лише для читання через Ґрунт
      </p>
    </div>
  </div>
</template>
