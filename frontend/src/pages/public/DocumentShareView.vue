<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Loader2, AlertCircle, Eye, Clock } from '@lucide/vue'
import AppBrand from '@/components/app/AppBrand.vue'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import { formatFull } from '@/core/datetime'

const route = useRoute()
const { t } = useI18n()
const { appName } = useSiteConfig()
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
    const resp = await fetch('/api/v1/method/grunt.api.v1.share.get_shared_document', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ token })
    })
    if (resp.status === 410) { error.value = 'Термін дії посилання закінчився'; return }
    if (resp.status === 404) { error.value = 'Посилання не знайдено або деактивовано'; return }
    if (!resp.ok) { error.value = `Помилка ${resp.status}`; return }
    const json = await resp.json()
    data.value = json.data
  } catch (e) {
    const errorMessage = e instanceof Error ? e.message : String(e)
    console.error('Failed to load shared document:', errorMessage, e)
    error.value = 'Помилка мережі'
  } finally {
    loading.value = false
  }
})

const SKIP_FIELDS = new Set(['id', 'name', 'owner', 'created_at', 'modified_at', 'modified_by', 'docstatus'])
const MULTILINE = new Set(['LongText', 'Text', 'HTML'])

function formatVal(fieldtype: string, val: string | null): string {
  if (val === null || val === undefined || val === '') return t('common.empty', '—')
  if (fieldtype === 'Check') return val === '1' || val === 'true' ? t('common.yes', 'Так') : t('common.no', 'Ні')
  return val
}
</script>

<template>
  <div class="min-h-screen bg-muted/30">
    <!-- Minimal header -->
    <header class="bg-card border-b border-border/60 px-6 py-3 flex items-center gap-2.5">
      <AppBrand mark-class="w-7 h-7" name-class="text-sm font-semibold" />
      <span class="text-muted-foreground/40 ml-1">·</span>
      <span class="text-muted-foreground flex items-center gap-1">
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
      <p class="text-muted-foreground">Зверніться до власника документа за новим посиланням.</p>
    </div>

    <!-- Document -->
    <div v-else-if="data" class="max-w-3xl mx-auto py-10 px-4">
      <!-- Doc header -->
      <div class="bg-card border border-border rounded-lg shadow-sm px-6 py-5 mb-6">
        <p class="font-medium text-muted-foreground uppercase tracking-wide mb-1">{{ data.doctype_label }}</p>
        <h1 class="text-2xl font-semibold text-foreground">{{ data.doc.name ?? data.doc_id }}</h1>
        <div v-if="data.expires_at" class="flex items-center gap-1.5 mt-2 text-muted-foreground">
          <Clock class="size-3" />
          Дійсно до {{ formatFull(data.expires_at) }}
        </div>
      </div>

      <!-- Fields -->
      <div class="bg-card border border-border rounded-lg shadow-sm overflow-hidden">
        <div class="px-6 py-4 border-b border-border/60">
          <h2 class="font-semibold text-foreground">Дані документа</h2>
        </div>
        <div class="divide-y divide-border/50">
          <div
            v-for="field in data.fields.filter(f => !SKIP_FIELDS.has(f.fieldname))"
            :key="field.fieldname"
            class="grid grid-cols-[180px_1fr] gap-4 px-6 py-3.5 hover:bg-muted/20 transition-colors"
          >
            <span class="text-muted-foreground font-medium truncate self-start pt-0.5">{{ field.label }}</span>
            <span
              :class="['text-foreground', MULTILINE.has(field.fieldtype) ? 'whitespace-pre-wrap' : '']"
            >{{ formatVal(field.fieldtype, data.doc[field.fieldname] ?? null) }}</span>
          </div>
        </div>
      </div>

      <!-- Footer note -->
      <p class="text-center text-muted-foreground mt-6">
        Цей документ надано у режимі лише для читання через {{ appName }}
      </p>
    </div>
  </div>
</template>
