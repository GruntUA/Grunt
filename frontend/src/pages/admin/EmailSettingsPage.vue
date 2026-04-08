<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import api from '@/core/api/client'
import { useToast } from '@/core/composables/useToast'
import {
  Mail, Plus, Trash2, RefreshCcw, Send, CheckCircle2,
  XCircle, Clock, ChevronLeft, ChevronRight,
  Wifi, WifiOff, Eye, EyeOff,
} from 'lucide-vue-next'

const { success: toastSuccess, error: toastError } = useToast()

// ── Tabs ─────────────────────────────────────────────────────────────────────
type Tab = 'accounts' | 'queue'
const activeTab = ref<Tab>('accounts')

// ── Email Accounts ────────────────────────────────────────────────────────────

interface EmailAccount {
  id: string
  email_address: string
  enable_outgoing: boolean
  smtp_server: string | null
  smtp_port: number
  use_tls: boolean
  smtp_user: string | null
  smtp_password: string | null
  enable_incoming: boolean
  imap_server: string | null
  imap_port: number
  use_ssl: boolean
}

const accounts = ref<EmailAccount[]>([])
const accountsLoading = ref(false)
const accountsError = ref('')

async function fetchAccounts() {
  accountsLoading.value = true
  accountsError.value = ''
  try {
    const res = await api.get('/api/v1/email/accounts')
    accounts.value = res.data.data
  } catch (e: any) {
    accountsError.value = e?.response?.data?.detail ?? 'Помилка завантаження'
  } finally {
    accountsLoading.value = false
  }
}

fetchAccounts()

// ── Account form ──────────────────────────────────────────────────────────────

const showForm = ref(false)
const editingId = ref<string | null>(null)
const showPassword = ref(false)
const formSaving = ref(false)

const form = reactive<Partial<EmailAccount>>({
  email_address: '',
  enable_outgoing: false,
  smtp_server: '',
  smtp_port: 587,
  use_tls: true,
  smtp_user: '',
  smtp_password: '',
  enable_incoming: false,
  imap_server: '',
  imap_port: 993,
  use_ssl: true,
})

function openNew() {
  editingId.value = null
  Object.assign(form, {
    email_address: '',
    enable_outgoing: false,
    smtp_server: '',
    smtp_port: 587,
    use_tls: true,
    smtp_user: '',
    smtp_password: '',
    enable_incoming: false,
    imap_server: '',
    imap_port: 993,
    use_ssl: true,
  })
  showPassword.value = false
  showForm.value = true
}

function openEdit(acc: EmailAccount) {
  editingId.value = acc.id
  Object.assign(form, { ...acc, smtp_password: '' })
  showPassword.value = false
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editingId.value = null
}

async function saveAccount() {
  formSaving.value = true
  try {
    const payload = { ...form }
    // Don't send masked placeholder back
    if (payload.smtp_password === '••••••••') delete payload.smtp_password

    if (editingId.value) {
      await api.put(`/api/v1/docs/EmailAccount/${editingId.value}`, payload)
      toastSuccess('Збережено')
    } else {
      await api.post('/api/v1/docs/EmailAccount', payload)
      toastSuccess('Створено')
    }
    closeForm()
    await fetchAccounts()
  } catch (e: any) {
    toastError(e?.response?.data?.detail ?? 'Помилка збереження')
  } finally {
    formSaving.value = false
  }
}

async function deleteAccount(id: string) {
  if (!confirm('Видалити обліковий запис?')) return
  try {
    await api.delete(`/api/v1/docs/EmailAccount/${id}`)
    toastSuccess('Видалено')
    await fetchAccounts()
  } catch {
    toastError('Помилка видалення')
  }
}

// ── Test connection ───────────────────────────────────────────────────────────

const testResult = ref<{ success: boolean; error?: string } | null>(null)
const testLoading = ref(false)

async function testConnection() {
  testResult.value = null
  testLoading.value = true
  try {
    const res = await api.post('/api/v1/email/test-connection', {
      smtp_server: form.smtp_server,
      smtp_port: form.smtp_port,
      use_tls: form.use_tls,
      smtp_user: form.smtp_user || undefined,
      smtp_password: form.smtp_password || undefined,
    })
    testResult.value = res.data
    if (res.data.success) toastSuccess('З\'єднання успішне')
    else toastError(res.data.error ?? 'Не вдалося підключитись')
  } catch (e: any) {
    testResult.value = { success: false, error: e?.response?.data?.detail ?? 'Помилка' }
  } finally {
    testLoading.value = false
  }
}

// ── Email Queue ───────────────────────────────────────────────────────────────

interface QueueItem {
  id: string
  recipient: string
  subject: string
  status: 'Pending' | 'Sent' | 'Error'
  error_message: string | null
  created_at: string | null
  email_account: string | null
}

const queueItems = ref<QueueItem[]>([])
const queueLoading = ref(false)
const queueError = ref('')
const queueStatus = ref('')
const queuePage = ref(1)
const queueTotal = ref(0)
const PER_PAGE = 25

async function fetchQueue() {
  queueLoading.value = true
  queueError.value = ''
  try {
    const params: Record<string, string | number> = { page: queuePage.value, per_page: PER_PAGE }
    if (queueStatus.value) params.status = queueStatus.value
    const res = await api.get('/api/v1/email/queue', { params })
    queueItems.value = res.data.data
    queueTotal.value = res.data.meta.total
  } catch (e: any) {
    queueError.value = e?.response?.data?.detail ?? 'Помилка завантаження'
  } finally {
    queueLoading.value = false
  }
}

watch(activeTab, (tab) => { if (tab === 'queue') fetchQueue() })
watch([queueStatus, queuePage], fetchQueue)

const queuePages = computed(() => Math.max(1, Math.ceil(queueTotal.value / PER_PAGE)))

async function retryItem(id: string) {
  try {
    await api.post(`/api/v1/email/queue/${id}/retry`)
    toastSuccess('Перепоставлено в чергу')
    fetchQueue()
  } catch {
    toastError('Помилка')
  }
}

function statusColor(status: string) {
  if (status === 'Sent') return 'text-green-600 bg-green-50'
  if (status === 'Error') return 'text-red-600 bg-red-50'
  return 'text-amber-600 bg-amber-50'
}

function statusIcon(status: string) {
  if (status === 'Sent') return CheckCircle2
  if (status === 'Error') return XCircle
  return Clock
}

function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleString('uk-UA', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-6">
      <Mail class="size-6 text-primary" />
      <h1 class="text-xl font-semibold">Налаштування пошти</h1>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 border-b mb-6">
      <button v-for="tab in (['accounts', 'queue'] as Tab[])" :key="tab"
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors" :class="activeTab === tab
          ? 'border-primary text-primary'
          : 'border-transparent text-muted-foreground hover:text-foreground'" @click="activeTab = tab">
        {{ tab === 'accounts' ? 'Облікові записи' : 'Черга листів' }}
      </button>
    </div>

    <!-- ── ACCOUNTS TAB ────────────────────────────────────────────────── -->
    <template v-if="activeTab === 'accounts'">
      <div class="flex justify-between items-center mb-4">
        <span class="text-sm text-muted-foreground">{{ accounts.length }} {{ accounts.length === 1 ? 'обліковий запис' :
          'облікових записів' }}</span>
        <button
          class="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          @click="openNew">
          <Plus class="size-4" /> Додати
        </button>
      </div>

      <div v-if="accountsLoading" class="text-center py-10 text-muted-foreground">Завантаження…</div>
      <div v-else-if="accountsError" class="text-center py-10 text-destructive">{{ accountsError }}</div>
      <div v-else-if="!accounts.length" class="text-center py-12 text-muted-foreground">
        <Mail class="size-10 mx-auto mb-3 opacity-30" />
        <p>Облікових записів ще немає</p>
        <button class="mt-3 text-sm text-primary underline" @click="openNew">Додати перший</button>
      </div>
      <div v-else class="grid gap-3">
        <div v-for="acc in accounts" :key="acc.id"
          class="border rounded-lg p-4 bg-card hover:shadow-sm transition-shadow">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="font-medium">{{ acc.email_address }}</p>
              <div class="flex gap-3 mt-1.5">
                <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                  :class="acc.enable_outgoing ? 'bg-green-50 text-green-700' : 'bg-muted text-muted-foreground'">
                  <component :is="acc.enable_outgoing ? Wifi : WifiOff" class="size-3" />
                  Вихідна {{ acc.enable_outgoing ? 'увімкнена' : 'вимкнена' }}
                </span>
                <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                  :class="acc.enable_incoming ? 'bg-blue-50 text-blue-700' : 'bg-muted text-muted-foreground'">
                  <Mail class="size-3" />
                  Вхідна {{ acc.enable_incoming ? 'увімкнена' : 'вимкнена' }}
                </span>
              </div>
              <p v-if="acc.smtp_server" class="mt-1 text-xs text-muted-foreground">
                SMTP: {{ acc.smtp_server }}:{{ acc.smtp_port }}
                <span v-if="acc.use_tls" class="ml-1 text-green-600">TLS</span>
              </p>
            </div>
            <div class="flex gap-2 shrink-0">
              <button class="text-sm px-3 py-1.5 border rounded-md hover:bg-muted transition-colors"
                @click="openEdit(acc)">
                Редагувати
              </button>
              <button class="p-1.5 text-muted-foreground hover:text-destructive transition-colors"
                @click="deleteAccount(acc.id)">
                <Trash2 class="size-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Account Form Dialog -->
      <Teleport to="body">
        <Transition enter-active-class="transition-opacity duration-200" enter-from-class="opacity-0"
          leave-active-class="transition-opacity duration-150" leave-to-class="opacity-0">
          <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
            <div class="bg-background rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
              <div class="flex items-center justify-between p-5 border-b">
                <h2 class="text-base font-semibold">
                  {{ editingId ? 'Редагувати' : 'Новий' }} обліковий запис
                </h2>
                <button class="text-muted-foreground hover:text-foreground" @click="closeForm">✕</button>
              </div>

              <div class="p-5 space-y-4">
                <!-- Email address -->
                <div>
                  <label class="block text-sm font-medium mb-1">Email адреса *</label>
                  <input v-model="form.email_address" type="email"
                    class="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="noreply@example.com" />
                </div>

                <!-- Outgoing section -->
                <div class="border rounded-lg p-4 space-y-3">
                  <label class="flex items-center gap-2 cursor-pointer">
                    <input v-model="form.enable_outgoing" type="checkbox" class="rounded" />
                    <span class="text-sm font-medium">Вихідна пошта (SMTP)</span>
                  </label>

                  <template v-if="form.enable_outgoing">
                    <div class="grid grid-cols-3 gap-3">
                      <div class="col-span-2">
                        <label class="block text-xs text-muted-foreground mb-1">SMTP сервер</label>
                        <input v-model="form.smtp_server" type="text"
                          class="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          placeholder="smtp.gmail.com" />
                      </div>
                      <div>
                        <label class="block text-xs text-muted-foreground mb-1">Порт</label>
                        <input v-model.number="form.smtp_port" type="number"
                          class="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                      </div>
                    </div>

                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="form.use_tls" type="checkbox" class="rounded" />
                      <span class="text-sm">Використовувати TLS</span>
                    </label>

                    <div>
                      <label class="block text-xs text-muted-foreground mb-1">Користувач</label>
                      <input v-model="form.smtp_user" type="text"
                        class="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        placeholder="user@example.com" />
                    </div>

                    <div>
                      <label class="block text-xs text-muted-foreground mb-1">Пароль</label>
                      <div class="relative">
                        <input v-model="form.smtp_password" :type="showPassword ? 'text' : 'password'"
                          class="w-full border rounded-md px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          placeholder="••••••••" />
                        <button type="button"
                          class="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                          @click="showPassword = !showPassword">
                          <component :is="showPassword ? EyeOff : Eye" class="size-4" />
                        </button>
                      </div>
                    </div>

                    <!-- Test connection -->
                    <div class="flex items-center gap-3">
                      <button type="button" :disabled="testLoading || !form.smtp_server"
                        class="flex items-center gap-1.5 text-sm px-3 py-1.5 border rounded-md hover:bg-muted disabled:opacity-50 transition-colors"
                        @click="testConnection">
                        <Send class="size-3.5" />
                        {{ testLoading ? 'Перевірка…' : 'Тест підключення' }}
                      </button>
                      <span v-if="testResult" class="flex items-center gap-1 text-sm">
                        <CheckCircle2 v-if="testResult.success" class="size-4 text-green-600" />
                        <XCircle v-else class="size-4 text-destructive" />
                        <span :class="testResult.success ? 'text-green-700' : 'text-destructive'">
                          {{ testResult.success ? 'З\'єднання успішне' : testResult.error }}
                        </span>
                      </span>
                    </div>
                  </template>
                </div>

                <!-- Incoming section -->
                <div class="border rounded-lg p-4 space-y-3">
                  <label class="flex items-center gap-2 cursor-pointer">
                    <input v-model="form.enable_incoming" type="checkbox" class="rounded" />
                    <span class="text-sm font-medium">Вхідна пошта (IMAP)</span>
                  </label>

                  <template v-if="form.enable_incoming">
                    <div class="grid grid-cols-3 gap-3">
                      <div class="col-span-2">
                        <label class="block text-xs text-muted-foreground mb-1">IMAP сервер</label>
                        <input v-model="form.imap_server" type="text"
                          class="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          placeholder="imap.gmail.com" />
                      </div>
                      <div>
                        <label class="block text-xs text-muted-foreground mb-1">Порт</label>
                        <input v-model.number="form.imap_port" type="number"
                          class="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                      </div>
                    </div>

                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="form.use_ssl" type="checkbox" class="rounded" />
                      <span class="text-sm">Використовувати SSL</span>
                    </label>
                  </template>
                </div>
              </div>

              <div class="flex justify-end gap-2 p-5 border-t">
                <button class="text-sm px-4 py-2 border rounded-md hover:bg-muted transition-colors" @click="closeForm">
                  Скасувати
                </button>
                <button :disabled="formSaving || !form.email_address"
                  class="text-sm px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  @click="saveAccount">
                  {{ formSaving ? 'Збереження…' : editingId ? 'Зберегти' : 'Створити' }}
                </button>
              </div>
            </div>
          </div>
        </Transition>
      </Teleport>
    </template>

    <!-- ── QUEUE TAB ──────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'queue'">
      <div class="flex items-center gap-3 mb-4">
        <!-- Status filter -->
        <select v-model="queueStatus"
          class="border rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          @change="queuePage = 1">
          <option value="">Всі статуси</option>
          <option value="Pending">Pending</option>
          <option value="Sent">Sent</option>
          <option value="Error">Error</option>
        </select>

        <button
          class="ml-auto flex items-center gap-1.5 text-sm px-3 py-1.5 border rounded-md hover:bg-muted transition-colors"
          @click="fetchQueue">
          <RefreshCcw class="size-3.5" /> Оновити
        </button>
      </div>

      <div v-if="queueLoading" class="text-center py-10 text-muted-foreground">Завантаження…</div>
      <div v-else-if="queueError" class="text-center py-10 text-destructive">{{ queueError }}</div>
      <div v-else-if="!queueItems.length" class="text-center py-12 text-muted-foreground">
        <Mail class="size-10 mx-auto mb-3 opacity-30" />
        <p>Черга порожня</p>
      </div>
      <div v-else class="space-y-2">
        <div v-for="item in queueItems" :key="item.id" class="border rounded-lg p-4 bg-card">
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full"
                  :class="statusColor(item.status)">
                  <component :is="statusIcon(item.status)" class="size-3" />
                  {{ item.status }}
                </span>
                <span class="text-xs text-muted-foreground">{{ fmtDate(item.created_at) }}</span>
              </div>
              <p class="text-sm font-medium truncate">{{ item.subject || '(без теми)' }}</p>
              <p class="text-xs text-muted-foreground truncate">→ {{ item.recipient }}</p>
              <p v-if="item.error_message" class="mt-1 text-xs text-destructive line-clamp-2">
                {{ item.error_message }}
              </p>
            </div>
            <button v-if="item.status === 'Error'"
              class="shrink-0 flex items-center gap-1 text-xs px-2.5 py-1.5 border rounded-md hover:bg-muted transition-colors"
              @click="retryItem(item.id)">
              <RefreshCcw class="size-3" /> Повторити
            </button>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="queuePages > 1" class="flex items-center justify-center gap-3 mt-4">
        <button :disabled="queuePage <= 1"
          class="p-1.5 border rounded-md disabled:opacity-40 hover:bg-muted transition-colors" @click="queuePage--">
          <ChevronLeft class="size-4" />
        </button>
        <span class="text-sm text-muted-foreground">{{ queuePage }} / {{ queuePages }}</span>
        <button :disabled="queuePage >= queuePages"
          class="p-1.5 border rounded-md disabled:opacity-40 hover:bg-muted transition-colors" @click="queuePage++">
          <ChevronRight class="size-4" />
        </button>
      </div>
    </template>
  </div>
</template>
