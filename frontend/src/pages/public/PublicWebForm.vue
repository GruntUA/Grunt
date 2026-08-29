<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { CheckCircle2, AlertCircle, Loader2 } from '@lucide/vue'
import { useSiteConfig } from '@/core/composables/useSiteConfig'

const route = useRoute()
const { appName } = useSiteConfig()
const formRoute = computed(() => route.params.route as string)

// ── Types ────────────────────────────────────────────────────────────────────
interface WebFormField {
  fieldname: string
  label: string
  fieldtype: string
  required?: boolean
  options?: string
  placeholder?: string
  description?: string
}

interface WebFormDef {
  title: string
  introduction?: string
  success_message?: string
  success_url?: string
  submit_label?: string
  login_required?: boolean
  field_definitions: WebFormField[]
}

// ── State ────────────────────────────────────────────────────────────────────
const formDef = ref<WebFormDef | null>(null)
const formData = ref<Record<string, unknown>>({})
const loading = ref(true)
const submitting = ref(false)
const submitted = ref(false)
const loadError = ref('')
const submitError = ref('')

// ── Load form definition ─────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const res = await fetch(`/api/v1/webform/${formRoute.value}`)
    if (!res.ok) {
      loadError.value = res.status === 404 ? 'Форму не знайдено' : 'Помилка завантаження форми'
      return
    }
    const json = await res.json()
    formDef.value = json.data
    // Initialize form data with empty values
    for (const f of (formDef.value?.field_definitions ?? [])) {
      if (!['Section', 'Column', 'Tab'].includes(f.fieldtype)) {
        formData.value[f.fieldname] = f.fieldtype === 'Check' ? false : ''
      }
    }
  } catch {
    loadError.value = 'Помилка мережі'
  } finally {
    loading.value = false
  }
})

// ── Submit ────────────────────────────────────────────────────────────────────
const validationErrors = ref<Record<string, string>>({})

function validate(): boolean {
  validationErrors.value = {}
  for (const f of (formDef.value?.field_definitions ?? [])) {
    if (f.required && !formData.value[f.fieldname] && formData.value[f.fieldname] !== 0) {
      validationErrors.value[f.fieldname] = `Поле "${f.label}" є обов'язковим`
    }
  }
  return Object.keys(validationErrors.value).length === 0
}

async function submit() {
  if (!validate()) return
  submitting.value = true
  submitError.value = ''
  try {
    const res = await fetch(`/api/v1/webform/${formRoute.value}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData.value),
    })
    const json = await res.json()
    if (!res.ok) {
      submitError.value = json.detail ?? 'Помилка надсилання'
      return
    }
    submitted.value = true
    if (formDef.value?.success_url) {
      setTimeout(() => { window.location.href = formDef.value!.success_url! }, 2000)
    }
  } catch {
    submitError.value = 'Помилка мережі'
  } finally {
    submitting.value = false
  }
}

// ── Field helpers ────────────────────────────────────────────────────────────
function getSelectOptions(field: WebFormField): string[] {
  return (field.options ?? '').split('\n').filter(Boolean)
}

const inputClass = 'w-full h-10 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 transition-colors'
const errorInputClass = 'border-destructive focus:ring-destructive/30'
</script>

<template>
  <div class="min-h-screen bg-muted flex items-start justify-center py-12 px-4">
    <div class="w-full max-w-xl">

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-20">
        <Loader2 class="size-8 text-primary animate-spin" />
      </div>

      <!-- Load error -->
      <div v-else-if="loadError" class="bg-background rounded-lg shadow-sm border p-10 text-center">
        <AlertCircle class="size-10 text-destructive mx-auto mb-3" />
        <p class="text-lg font-semibold">{{ loadError }}</p>
      </div>

      <!-- Success state -->
      <div v-else-if="submitted" class="bg-background rounded-lg shadow-sm border p-10 text-center">
        <CheckCircle2 class="size-12 text-emerald-500 mx-auto mb-4" />
        <h2 class="text-xl font-semibold mb-2">Дякуємо!</h2>
        <p class="text-muted-foreground">
          {{ formDef?.success_message || 'Форму успішно надіслано.' }}
        </p>
      </div>

      <!-- Form -->
      <div v-else-if="formDef" class="bg-background rounded-lg shadow-sm border overflow-hidden">
        <!-- Header -->
        <div class="px-8 py-7 border-b bg-primary/5">
          <h1 class="text-2xl font-semibold text-foreground">{{ formDef.title }}</h1>
          <p v-if="formDef.introduction" class="mt-2 text-muted-foreground leading-relaxed">
            {{ formDef.introduction }}
          </p>
        </div>

        <!-- Fields -->
        <form class="px-8 py-6 space-y-5" @submit.prevent="submit">

          <template v-for="field in formDef.field_definitions" :key="field.fieldname">

            <!-- Section break -->
            <div v-if="field.fieldtype === 'Section'" class="pt-2">
              <p v-if="field.label" class="text-xs font-semibold uppercase tracking-widest text-muted-foreground border-b pb-2">
                {{ field.label }}
              </p>
              <hr v-else class="border-border" />
            </div>

            <!-- Data fields -->
            <div v-else class="space-y-1.5">
              <label class="flex items-center gap-1 font-medium text-foreground">
                {{ field.label }}
                <span v-if="field.required" class="text-destructive">*</span>
              </label>

              <!-- Text -->
              <input
                v-if="['Text', 'Data'].includes(field.fieldtype)"
                v-model="formData[field.fieldname] as string"
                type="text"
                :placeholder="field.placeholder ?? ''"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- LongText -->
              <textarea
                v-else-if="field.fieldtype === 'LongText'"
                v-model="formData[field.fieldname] as string"
                :placeholder="field.placeholder ?? ''"
                rows="4"
                :class="[inputClass, 'h-auto py-2 resize-none', validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Int / Float -->
              <input
                v-else-if="['Int', 'Float'].includes(field.fieldtype)"
                v-model="formData[field.fieldname] as string"
                type="number"
                :step="field.fieldtype === 'Float' ? 'any' : '1'"
                :placeholder="field.placeholder ?? ''"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Date -->
              <input
                v-else-if="field.fieldtype === 'Date'"
                v-model="formData[field.fieldname] as string"
                type="date"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Datetime -->
              <input
                v-else-if="field.fieldtype === 'Datetime'"
                v-model="formData[field.fieldname] as string"
                type="datetime-local"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Select -->
              <select
                v-else-if="field.fieldtype === 'Select'"
                v-model="formData[field.fieldname] as string"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              >
                <option value="">— Виберіть —</option>
                <option v-for="opt in getSelectOptions(field)" :key="opt" :value="opt">{{ opt }}</option>
              </select>

              <!-- Check -->
              <label v-else-if="field.fieldtype === 'Check'" class="flex items-center gap-2 cursor-pointer">
                <input
                  v-model="formData[field.fieldname] as boolean"
                  type="checkbox"
                  class="size-4 rounded border-border accent-primary"
                />
                <span class="text-muted-foreground">{{ field.description || field.label }}</span>
              </label>

              <!-- Email -->
              <input
                v-else-if="field.fieldtype === 'Email'"
                v-model="formData[field.fieldname] as string"
                type="email"
                :placeholder="field.placeholder ?? 'email@example.com'"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Phone -->
              <input
                v-else-if="field.fieldtype === 'Phone'"
                v-model="formData[field.fieldname] as string"
                type="tel"
                :placeholder="field.placeholder ?? '+380...'"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Fallback: text input -->
              <input
                v-else
                v-model="formData[field.fieldname] as string"
                type="text"
                :placeholder="field.placeholder ?? ''"
                :class="[inputClass, validationErrors[field.fieldname] ? errorInputClass : '']"
              />

              <!-- Description -->
              <p v-if="field.description && field.fieldtype !== 'Check'" class="text-xs text-muted-foreground">
                {{ field.description }}
              </p>

              <!-- Validation error -->
              <p v-if="validationErrors[field.fieldname]" class="text-xs text-destructive flex items-center gap-1">
                <AlertCircle class="size-3 shrink-0" />
                {{ validationErrors[field.fieldname] }}
              </p>
            </div>
          </template>

          <!-- Submit error -->
          <div v-if="submitError"
            class="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive">
            <AlertCircle class="size-4 shrink-0 mt-0.5" />
            {{ submitError }}
          </div>

          <!-- Submit button -->
          <div class="pt-2">
            <button
              type="submit"
              :disabled="submitting"
              class="w-full h-11 rounded-lg bg-primary text-primary-foreground font-semibold hover:bg-primary/90 transition-colors disabled:opacity-60 disabled:pointer-events-none flex items-center justify-center gap-2"
            >
              <Loader2 v-if="submitting" class="size-4 animate-spin" />
              {{ formDef.submit_label || 'Надіслати' }}
            </button>
          </div>
        </form>
      </div>

      <!-- Footer -->
      <p class="text-center text-xs text-muted-foreground mt-6 opacity-60">Powered by {{ appName }}</p>
    </div>
  </div>
</template>
