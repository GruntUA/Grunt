<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { appsApi, type GruntApp } from '@/core/api'
import { X } from '@lucide/vue'

const builder = useBuilderStore()

// --- Apps ---

const apps = ref<GruntApp[]>([])
const isLoadingApps = ref(false)

onMounted(async () => {
  isLoadingApps.value = true
  try {
    apps.value = await appsApi.list()
  } finally {
    isLoadingApps.value = false
  }
})

const selectedApp = computed(() => {
  const module = builder.doctype?.module ?? ''
  if (!module) return pendingAppName.value ? apps.value.find(a => a.name === pendingAppName.value) ?? null : null
  return apps.value.find(app => app.modules.includes(module)) ?? null
})

// Tracks which app is selected, even before a module is chosen
const pendingAppName = ref<string | null>(null)

// Sync pendingAppName from existing doctype module on load
watch(apps, (list: GruntApp[]) => {
  if (pendingAppName.value !== null) return
  const module = builder.doctype?.module ?? ''
  if (!module) return
  const app = list.find((a: GruntApp) => a.modules.includes(module))
  if (app) pendingAppName.value = app.name
}, { immediate: true })

function setApp(appName: string | null) {
  pendingAppName.value = appName
  if (!appName) {
    builder.updateDocType({ module: '' })
    return
  }
  const app = apps.value.find(a => a.name === appName)
  if (!app) return
  if (app.modules.length === 1) {
    builder.updateDocType({ module: app.modules[0] })
  } else {
    // Either no modules or multiple — clear module until user picks/creates one
    builder.updateDocType({ module: '' })
  }
}

function setModule(moduleName: string) {
  builder.updateDocType({ module: moduleName })
}

// --- Create module ---
const newModuleName = ref('')
const isCreatingModule = ref(false)

async function createModule() {
  const name = newModuleName.value.trim()
  if (!name || !pendingAppName.value) return
  isCreatingModule.value = true
  try {
    const updated = await appsApi.addModule(pendingAppName.value, name)
    // Patch apps list in place
    const idx = apps.value.findIndex(a => a.name === updated.name)
    if (idx !== -1) apps.value[idx] = { ...apps.value[idx], modules: updated.modules }
    builder.updateDocType({ module: name })
    newModuleName.value = ''
  } finally {
    isCreatingModule.value = false
  }
}

// --- Name derivation ---

function labelToName(label: string): string {
  return label
    .split(/[\s_\-]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join('')
    .replace(/[^A-Za-z0-9]/g, '')
}

function onLabelChange(val: string) {
  if (builder.isNew) {
    // Auto-sync name while it hasn't been manually diverged from the label
    const currentName = builder.doctype?.name ?? ''
    const prevDerived = labelToName(builder.doctype?.label ?? '')
    if (currentName === '' || currentName === prevDerived) {
      builder.updateDocType({ label: val, name: labelToName(val) })
      return
    }
  }
  builder.updateDocType({ label: val })
}

// --- Computed helpers ---

const dataFields = computed(() =>
  (builder.doctype?.fields ?? []).filter(
    (f) => !['Section', 'Column', 'Tab', 'Table'].includes(f.fieldtype) && !!f.fieldname,
  ),
)

const imageFields = computed(() =>
  (builder.doctype?.fields ?? []).filter(
    (f) => ['Image', 'Attach Image'].includes(f.fieldtype) && !!f.fieldname,
  ),
)

const autonameStrategy = computed(() => {
  const v = builder.doctype?.autoname ?? ''
  if (v.startsWith('field:')) return 'field:'
  if (v.startsWith('format:')) return 'format:'
  return v || '__auto__'
})

const autonameValue = computed(() => {
  const v = builder.doctype?.autoname ?? ''
  if (v.startsWith('field:')) return v.slice(6)
  if (v.startsWith('format:')) return v.slice(7)
  return ''
})

const searchFields = computed(() => {
  const raw = builder.doctype?.search_fields
  if (!raw) return [] as string[]
  if (Array.isArray(raw)) return raw as string[]
  return (raw as string)
    .split(',')
    .map((s: string) => s.trim())
    .filter(Boolean)
})

const availableSearchFields = computed(() =>
  dataFields.value.filter((f) => !searchFields.value.includes(f.fieldname)),
)

// --- Naming helpers ---

function setAutonameStrategy(strategy: string | number | bigint | Record<string, any> | null) {
  const s = String(strategy ?? '')
  if (s === '__auto__') {
    builder.updateDocType({ autoname: null })
    return
  }
  if (s === 'field:') {
    builder.updateDocType({
      autoname: 'field:' + (dataFields.value[0]?.fieldname ?? ''),
    })
  } else if (s === 'format:') {
    builder.updateDocType({ autoname: 'format:' })
  } else {
    builder.updateDocType({ autoname: s || null })
  }
}

function setAutonameValue(val: string | number | bigint | Record<string, any> | null) {
  const v = String(val ?? '')
  const s = autonameStrategy.value
  if (s === 'field:') builder.updateDocType({ autoname: 'field:' + v })
  else if (s === 'format:') builder.updateDocType({ autoname: 'format:' + v })
}

// --- Search fields helpers ---

const searchFieldSelect = ref('')

function addSearchField(fieldname: string | number | null) {
  if (!fieldname) return
  const updated = [...searchFields.value, String(fieldname)]
  builder.updateDocType({ search_fields: updated })
  searchFieldSelect.value = ''
}

function removeSearchField(fieldname: string) {
  const updated = searchFields.value.filter((f) => f !== fieldname)
  builder.updateDocType({ search_fields: updated })
}
</script>

<template>
  <div class="mx-auto max-w-2xl p-6">
    <!-- Ідентичність -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Ідентичність</h3>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Назва</label>
        <Input :model-value="builder.doctype?.label ?? ''" class="w-full" @update:model-value="onLabelChange(String($event))" />
      </div>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Системна назва</label>
        <Input :model-value="builder.doctype?.name ?? ''" :disabled="!builder.isNew" placeholder="PascalCase" class="w-full"
          @update:model-value="builder.isNew && builder.updateDocType({ name: String($event) })" />
      </div>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Додаток</label>
        <Select :model-value="pendingAppName ?? '__none__'" @update:model-value="setApp(String($event) === '__none__' ? null : (String($event) || null))" :disabled="isLoadingApps">
          <SelectTrigger class="w-full">
            <SelectValue :placeholder="isLoadingApps ? 'Завантажує...' : 'Оберіть додаток'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [{ value: '__none__', label: 'Немає додатку' }, ...apps.map(a => ({ value: a.name, label: a.title }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <!-- Module selector — shown only when an app is selected -->
      <div v-if="pendingAppName" class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Модуль</label>

        <!-- App has modules → show select -->
        <Select :model-value="builder.doctype?.module || ''" v-if="selectedApp && selectedApp.modules.length > 0" @update:model-value="setModule(String($event))">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Оберіть модуль" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in selectedApp.modules" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>

        <!-- App has no modules → create form -->
        <div v-else class="space-y-2">
          <p class="text-sm text-muted-foreground">У цьому додатку немає модулів. Введіть назву нового модуля:</p>
          <div class="flex gap-2">
            <Input v-model="newModuleName" placeholder="Назва модуля" class="flex-1" @keydown.enter="createModule" />
            <Button type="button" :disabled="!newModuleName.trim() || isCreatingModule" @click="createModule">
              {{ isCreatingModule ? 'Створення...' : 'Створити' }}
            </Button>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <span class="text-sm font-medium text-foreground">Сінглтон</span>
          <Switch :model-value="!!builder.doctype?.is_singleton"
            @update:model-value="builder.updateDocType({ is_singleton: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <span class="text-sm font-medium text-foreground">Подання</span>
          <Switch :model-value="!!builder.doctype?.is_submittable"
            @update:model-value="builder.updateDocType({ is_submittable: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <span class="text-sm font-medium text-foreground">Дочірній</span>
          <Switch :model-value="!!builder.doctype?.is_child"
            @update:model-value="builder.updateDocType({ is_child: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <span class="text-sm font-medium text-foreground">Ієрархія (дерево)</span>
          <Switch :model-value="!!builder.doctype?.is_tree"
            @update:model-value="builder.updateDocType({ is_tree: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <span class="text-sm font-medium text-foreground">Відстеження змін</span>
          <Switch :model-value="!!builder.doctype?.track_changes"
            @update:model-value="builder.updateDocType({ track_changes: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <span class="text-sm font-medium text-foreground">Швидке створення</span>
            <p class="text-xs text-muted-foreground mt-0.5">Відкривати діалог замість повної форми</p>
          </div>
          <Switch :model-value="!!builder.doctype?.quick_entry"
            @update:model-value="builder.updateDocType({ quick_entry: $event })" />
        </div>
      </div>
    </section>

    <Separator class="!my-6" />

    <!-- Збереження та ідентифікація -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Збереження та ідентифікація</h3>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Стратегія автоіменування</label>
        <Select :model-value="autonameStrategy" @update:model-value="setAutonameStrategy">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Оберіть стратегію" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [
            { value: '__auto__', label: 'Авто' },
            { value: 'autoincrement', label: 'Авто-інкремент' },
            { value: 'field:', label: 'На основі поля' },
            { value: 'format:', label: 'Шаблон' },
            { value: 'hash', label: 'Хеш' },
            { value: 'prompt', label: 'Запит у користувача' },
          ]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div v-if="autonameStrategy === 'field:'" class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Поле для імені</label>
        <Select :model-value="autonameValue" @update:model-value="setAutonameValue">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in dataFields.map(f => ({ value: f.fieldname, label: f.label || f.fieldname }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div v-if="autonameStrategy === 'format:'" class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Шаблон</label>
        <Input :model-value="autonameValue" placeholder="CONTR-.YYYY.-.####" class="w-full"
          @update:model-value="setAutonameValue($event as any)" />
      </div>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Поле заголовка</label>
        <Select :model-value="builder.doctype?.title_field || '__name__'" @update:model-value="builder.updateDocType({ title_field: String($event) === '__name__' ? undefined : String($event) })">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [{ value: '__name__', label: 'name' }, ...dataFields.map(f => ({ value: f.fieldname, label: f.label || f.fieldname }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Поле фото</label>
        <Select :model-value="builder.doctype?.image_field || '__none__'" @update:model-value="builder.updateDocType({ image_field: String($event) === '__none__' ? null : String($event) })">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [{ value: '__none__', label: 'Немає' }, ...imageFields.map(f => ({ value: f.fieldname, label: f.label || f.fieldname }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
        <p v-if="imageFields.length === 0" class="text-xs text-muted-foreground mt-1">
          Додайте поле типу «Image» або «Attach Image» у форму, щоб обрати його тут.
        </p>
      </div>
    </section>

    <Separator class="!my-6" />

    <!-- Відображення -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Відображення</h3>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Вигляд за замовчуванням</label>
        <Select :model-value="builder.doctype?.default_view ?? 'list'" @update:model-value="builder.updateDocType({ default_view: String($event) === 'list' ? null : String($event) as 'kanban' | 'calendar' | 'tree' })">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Оберіть вигляд" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [
            { value: 'list', label: 'Список' },
            { value: 'kanban', label: 'Канбан' },
            { value: 'calendar', label: 'Календар' },
            { value: 'tree', label: 'Дерево' },
          ]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </section>

    <Separator class="!my-6" />

    <!-- Керованість та безпека (advanced) -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Керованість та безпека</h3>

      <div class="grid grid-cols-2 gap-4 mb-4">
        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <span class="text-sm font-medium text-foreground">Віртуальний DocType</span>
            <p class="text-xs text-muted-foreground mt-0.5">Без фізичної таблиці в БД, дані повертає контролер</p>
          </div>
          <Switch :model-value="!!builder.doctype?.is_virtual"
            @update:model-value="builder.updateDocType({ is_virtual: $event })" />
        </div>
      </div>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Фізична таблиця</label>
        <Input
          :model-value="builder.doctype?.table_name ?? ''"
          disabled
          placeholder="Згенерується після збереження"
          class="w-full"
        />
        <p class="text-xs text-muted-foreground mt-1">Службове поле тільки для перегляду. Назва визначається системою.</p>
      </div>

      <div class="rounded-md border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
        Права доступу керуються у вкладці «Permissions», а налаштування виглядів (list/tree/kanban/calendar/statuses) — у вкладці «Views».
      </div>
    </section>

    <Separator class="!my-6" />

    <!-- Пошук (Search) -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Пошук</h3>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-sm font-medium text-muted-foreground uppercase tracking-wide">Поля пошуку</label>

        <div v-if="searchFields.length" class="mb-2 flex flex-wrap gap-2">
          <Badge v-for="sf in searchFields" :key="sf" variant="secondary" class="flex items-center gap-1">
            {{ sf }}
            <button type="button" class="ml-1 hover:text-destructive" @click="removeSearchField(sf)">
              <X class="h-3 w-3" />
            </button>
          </Badge>
        </div>

        <Select :model-value="searchFieldSelect" @update:model-value="addSearchField($event as string)">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Додати поле для пошуку" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in availableSearchFields.map(f => ({ value: f.fieldname, label: f.label || f.fieldname }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </section>
  </div>
</template>
