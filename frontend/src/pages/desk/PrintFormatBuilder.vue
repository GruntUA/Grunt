<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import { docsApi } from '@/core/api/docs'
import { useToast } from '@/core/composables/useToast'
import client from '@/core/api/client'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2, Save, Eye, EyeOff, RefreshCw, ChevronLeft, FileText } from 'lucide-vue-next'
import type { GruntDocument } from '@/types'

const props = defineProps<{
  id: string
  workspaceName?: string
}>()

const router = useRouter()
const dtStore = useDocTypeStore()
const toast = useToast()

// ── State ─────────────────────────────────────────────────────────────────

const record = ref<GruntDocument | null>(null)
const template = ref('')
const doctype = ref('')
const sampleDocId = ref('')
const isSaving = ref(false)
const isPreviewLoading = ref(false)
const previewHtml = ref('')
const showPreview = ref(true)
const sampleDocs = ref<GruntDocument[]>([])
const allDoctypes = computed(() => dtStore.doctypes.filter(dt => !dt.is_child))

// ── Default template ──────────────────────────────────────────────────────

const DEFAULT_TEMPLATE = `<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: Arial, sans-serif; font-size: 13px; color: #222; margin: 2cm; }
    h1 { font-size: 20px; border-bottom: 2px solid #333; padding-bottom: 8px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th { background: #f0f0f0; padding: 6px 10px; text-align: left; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #ccc; }
    td { padding: 6px 10px; border-bottom: 1px solid #eee; }
    .meta { font-size: 11px; color: #666; margin-top: 20px; }
  </style>
</head>
<body>
  <h1>{{ doctype_label }}: {{ doc.name }}</h1>
  <table>
    <thead><tr><th>Поле</th><th>Значення</th></tr></thead>
    <tbody>
      {% for field in fields %}
        {% if field.fieldtype not in ['Section', 'Column', 'Tab', 'Table'] and doc[field.fieldname] %}
        <tr>
          <td>{{ field.label }}</td>
          <td>{{ doc[field.fieldname] }}</td>
        </tr>
        {% endif %}
      {% endfor %}
    </tbody>
  </table>
  <div class="meta">Згенеровано: {{ now.strftime('%d.%m.%Y %H:%M') }} | Власник: {{ doc.owner }}</div>
</body>
</html>`

// ── Load record ───────────────────────────────────────────────────────────

async function loadRecord() {
  if (props.id === 'new') {
    template.value = DEFAULT_TEMPLATE
    return
  }
  try {
    record.value = await docsApi.get('PrintFormat', props.id)
    template.value = String(record.value.template ?? DEFAULT_TEMPLATE)
    doctype.value = String(record.value.doctype ?? '')
    if (doctype.value) await loadSampleDocs()
  } catch {
    toast.error('Не вдалося завантажити формат друку')
  }
}

async function loadSampleDocs() {
  if (!doctype.value) return
  try {
    const res = await docsApi.list(doctype.value, { page: 1, per_page: 10, fields: 'id,name' })
    sampleDocs.value = (res.data ?? []) as GruntDocument[]
    if (!sampleDocId.value && sampleDocs.value.length) {
      sampleDocId.value = String(sampleDocs.value[0].id)
    }
  } catch { /* silent */ }
}

// ── Preview ───────────────────────────────────────────────────────────────

async function refreshPreview() {
  if (!doctype.value || !template.value) return
  isPreviewLoading.value = true
  try {
    const res = await client.post(
      `/api/v1/docs/${doctype.value}/print-preview`,
      { template: template.value, doc_id: sampleDocId.value || undefined },
      { responseType: 'text' }
    )
    previewHtml.value = res.data as string
  } catch (e: any) {
    previewHtml.value = `<pre style="color:red;padding:1rem">Помилка: ${e?.message}</pre>`
  } finally {
    isPreviewLoading.value = false
  }
}

// Auto-refresh preview with debounce
let previewTimer: ReturnType<typeof setTimeout> | null = null
watch([template, sampleDocId], () => {
  if (!showPreview.value) return
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(refreshPreview, 800)
})

watch(doctype, async () => {
  await loadSampleDocs()
  await loadDtFields()
  refreshPreview()
})

// ── Save ──────────────────────────────────────────────────────────────────

async function save() {
  if (!doctype.value) {
    toast.error('Оберіть тип документа')
    return
  }
  isSaving.value = true
  try {
    const data = { doctype: doctype.value, template: template.value, template_type: 'html' }
    if (props.id === 'new') {
      const created = await docsApi.create('PrintFormat', data)
      toast.success('Формат друку створено')
      router.replace(`/${props.workspaceName ?? 'grunt'}/list/PrintFormat/${created.id}`)
    } else {
      await docsApi.update('PrintFormat', props.id, data)
      toast.success('Збережено')
    }
  } catch {
    toast.error('Помилка збереження')
  } finally {
    isSaving.value = false
  }
}

// ── Copy default template ─────────────────────────────────────────────────

function resetToDefault() {
  template.value = DEFAULT_TEMPLATE
}

// ── Variable hints ────────────────────────────────────────────────────────

const selectedDtFields = ref<any[]>([])

async function loadDtFields() {
  if (!doctype.value) {
    selectedDtFields.value = []
    return
  }
  try {
    const fullDt = await dtStore.get(doctype.value)
    const SKIP = new Set(['Section', 'Column', 'Tab', 'Table'])
    selectedDtFields.value = (fullDt?.fields ?? []).filter((f: any) => !SKIP.has(f.fieldtype))
  } catch {
    selectedDtFields.value = []
  }
}

function insertVariable(fieldname: string) {
  template.value += `{{ doc.${fieldname} }}`
}

// ── Mount ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  if (dtStore.doctypes.length === 0) await dtStore.loadAll()
  await loadRecord()
  await loadDtFields()
  if (doctype.value) refreshPreview()
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-3 border-b bg-card shrink-0">
      <div class="flex items-center gap-3">
        <button class="text-muted-foreground hover:text-foreground transition-colors" @click="router.back()">
          <ChevronLeft class="size-5" />
        </button>
        <div class="flex items-center gap-2">
          <FileText class="size-5 text-primary" />
          <h1 class="text-base font-semibold text-foreground">
            {{ id === 'new' ? 'Новий формат друку' : 'Редактор шаблону' }}
          </h1>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- DocType selector -->
        <Select v-model="doctype" class="w-52">
          <SelectTrigger class="h-8 text-sm">
            <SelectValue placeholder="Тип документа..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="dt in allDoctypes" :key="dt.name" :value="dt.name">
              {{ dt.label }}
            </SelectItem>
          </SelectContent>
        </Select>

        <!-- Sample doc selector -->
        <Select v-if="sampleDocs.length" v-model="sampleDocId" class="w-40">
          <SelectTrigger class="h-8 text-sm">
            <SelectValue placeholder="Зразок..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="d in sampleDocs" :key="String(d.id)" :value="String(d.id)">
              {{ d.name ?? d.id }}
            </SelectItem>
          </SelectContent>
        </Select>

        <Button variant="outline" size="sm" class="h-8 text-foreground" @click="resetToDefault">
          <RefreshCw class="size-3.5 mr-1.5" />
          Скинути
        </Button>

        <Button variant="outline" size="sm" class="h-8 text-foreground" @click="showPreview = !showPreview">
          <EyeOff v-if="showPreview" class="size-3.5 mr-1.5" />
          <Eye v-else class="size-3.5 mr-1.5" />
          {{ showPreview ? 'Сховати' : 'Показати' }} preview
        </Button>

        <Button size="sm" class="h-8" :disabled="isSaving" @click="save">
          <Loader2 v-if="isSaving" class="size-3.5 animate-spin mr-1.5" />
          <Save v-else class="size-3.5 mr-1.5" />
          Зберегти
        </Button>
      </div>
    </div>

    <!-- Main split view -->
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <!-- Left: editor -->
      <div class="flex flex-col min-h-0" :class="showPreview ? 'w-1/2 border-r' : 'w-full'">
        <!-- Variable hints -->
        <div v-if="selectedDtFields.length" class="px-3 py-2 border-b bg-muted/30 flex flex-wrap gap-1.5 shrink-0">
          <span class="text-xs text-muted-foreground font-medium self-center mr-1">Змінні:</span>
          <button v-for="f in selectedDtFields.slice(0, 12)" :key="f.fieldname"
            class="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-mono"
            @click="insertVariable(f.fieldname)">
            {{ f.fieldname }}
          </button>
          <span v-if="selectedDtFields.length > 12" class="text-[10px] text-muted-foreground self-center">
            +{{ selectedDtFields.length - 12 }} ще
          </span>
        </div>

        <!-- Code editor -->
        <textarea v-model="template" spellcheck="false"
          class="flex-1 w-full font-mono text-xs bg-[#1e1e2e] text-[#cdd6f4] p-4 resize-none focus:outline-none"
          style="tab-size: 2;" placeholder="Введіть Jinja2 HTML шаблон..." />
      </div>

      <!-- Right: preview -->
      <div v-if="showPreview" class="flex-1 flex flex-col min-h-0 bg-white">
        <div class="flex items-center gap-2 px-3 py-1.5 border-b bg-muted/20 shrink-0">
          <span class="text-xs font-medium text-muted-foreground">Live Preview</span>
          <Loader2 v-if="isPreviewLoading" class="size-3.5 animate-spin text-muted-foreground" />
          <button class="ml-auto text-muted-foreground hover:text-foreground transition-colors" @click="refreshPreview">
            <RefreshCw class="size-3.5" />
          </button>
        </div>
        <div v-if="!doctype" class="flex-1 flex items-center justify-center text-sm text-muted-foreground italic">
          Оберіть тип документа для попереднього перегляду
        </div>
        <iframe v-else :srcdoc="previewHtml" class="flex-1 w-full border-none" sandbox="allow-same-origin" />
      </div>
    </div>
  </div>
</template>
