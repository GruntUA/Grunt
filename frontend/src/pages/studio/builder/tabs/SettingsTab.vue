<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { appsApi, type GruntApp } from '@/core/api'
import { Input } from '@/components/ui/input'
import { FormField } from '@/components/ui/form-field'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { X } from 'lucide-vue-next'

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
    <!-- Загальне (General) -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Загальне</h3>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Назва</Label>
        <Input :model-value="builder.doctype?.label ?? ''" @update:model-value="onLabelChange(String($event))" />
      </FormField>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Системна назва</Label>
        <Input :model-value="builder.doctype?.name ?? ''" :disabled="!builder.isNew" placeholder="PascalCase"
          @update:model-value="builder.isNew && builder.updateDocType({ name: String($event) })" />
      </FormField>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Додаток</Label>
        <Select :model-value="pendingAppName ?? '__none__'"
          @update:model-value="setApp(String($event) === '__none__' ? null : (String($event) || null))"
          :disabled="isLoadingApps">
          <SelectTrigger>
            <SelectValue :placeholder="isLoadingApps ? 'Завантажує...' : 'Оберіть додаток'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">Немає додатку</SelectItem>
            <SelectItem v-for="app in apps" :key="app.name" :value="app.name">
              {{ app.title }}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>

      <!-- Module selector — shown only when an app is selected -->
      <FormField v-if="pendingAppName" class="mb-4">
        <Label class="text-muted-foreground">Модуль</Label>

        <!-- App has modules → show select -->
        <Select v-if="selectedApp && selectedApp.modules.length > 0" :model-value="builder.doctype?.module || ''"
          @update:model-value="setModule(String($event))">
          <SelectTrigger>
            <SelectValue placeholder="Оберіть модуль" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="mod in selectedApp.modules" :key="mod" :value="mod">
              {{ mod }}
            </SelectItem>
          </SelectContent>
        </Select>

        <!-- App has no modules → create form -->
        <div v-else class="space-y-2">
          <p class="text-sm text-muted-foreground">У цьому додатку немає модулів. Введіть назву нового модуля:</p>
          <div class="flex gap-2">
            <Input v-model="newModuleName" placeholder="Назва модуля" @keydown.enter="createModule" />
            <Button type="button" :disabled="!newModuleName.trim() || isCreatingModule" @click="createModule">
              {{ isCreatingModule ? 'Створення...' : 'Створити' }}
            </Button>
          </div>
        </div>
      </FormField>

      <div class="grid grid-cols-2 gap-4">
        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Сінглтон</Label>
          <Switch :checked="!!builder.doctype?.is_singleton"
            @update:checked="builder.updateDocType({ is_singleton: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Подання</Label>
          <Switch :checked="!!builder.doctype?.is_submittable"
            @update:checked="builder.updateDocType({ is_submittable: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Дочірній</Label>
          <Switch :checked="!!builder.doctype?.is_child"
            @update:checked="builder.updateDocType({ is_child: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Ієрархія (дерево)</Label>
          <Switch :checked="!!builder.doctype?.is_tree"
            @update:checked="builder.updateDocType({ is_tree: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Відстеження змін</Label>
          <Switch :checked="!!builder.doctype?.track_changes"
            @update:checked="builder.updateDocType({ track_changes: $event })" />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <Label class="text-sm text-foreground">Швидке створення</Label>
            <p class="text-xs text-muted-foreground mt-0.5">Відкривати діалог замість повної форми</p>
          </div>
          <Switch :checked="!!builder.doctype?.quick_entry"
            @update:checked="builder.updateDocType({ quick_entry: $event })" />
        </div>
      </div>
    </section>

    <Separator class="my-6" />

    <!-- Нумерація (Naming) -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Нумерація</h3>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Стратегія автоіменування</Label>
        <Select :model-value="autonameStrategy" @update:model-value="setAutonameStrategy">
          <SelectTrigger>
            <SelectValue placeholder="Оберіть стратегію" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__auto__">Авто</SelectItem>
            <SelectItem value="autoincrement">Авто-інкремент</SelectItem>
            <SelectItem value="field:">На основі поля</SelectItem>
            <SelectItem value="format:">Шаблон</SelectItem>
            <SelectItem value="hash">Хеш</SelectItem>
            <SelectItem value="prompt">Запит у користувача</SelectItem>
          </SelectContent>
        </Select>
      </FormField>

      <FormField v-if="autonameStrategy === 'field:'" class="mb-4">
        <Label class="text-muted-foreground">Поле для імені</Label>
        <Select :model-value="autonameValue" @update:model-value="setAutonameValue">
          <SelectTrigger>
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="field in dataFields" :key="field.fieldname" :value="field.fieldname">
              {{ field.label || field.fieldname }}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>

      <FormField v-if="autonameStrategy === 'format:'" class="mb-4">
        <Label class="text-muted-foreground">Шаблон</Label>
        <Input :model-value="autonameValue" placeholder="CONTR-.YYYY.-.####"
          @update:model-value="setAutonameValue($event as any)" />
      </FormField>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Поле заголовка</Label>
        <Select :model-value="builder.doctype?.title_field || '__name__'"
          @update:model-value="builder.updateDocType({ title_field: String($event) === '__name__' ? undefined : String($event) })">
          <SelectTrigger>
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__name__">name</SelectItem>
            <SelectItem v-for="field in dataFields" :key="field.fieldname" :value="field.fieldname">
              {{ field.label || field.fieldname }}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>
    </section>

    <Separator class="my-6" />

    <!-- Вигляд за замовчуванням -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Вигляд</h3>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Вигляд за замовчуванням</Label>
        <Select :model-value="builder.doctype?.default_view ?? 'list'"
          @update:model-value="builder.updateDocType({ default_view: String($event) === 'list' ? null : String($event) as 'kanban' | 'calendar' | 'tree' })">
          <SelectTrigger>
            <SelectValue placeholder="Оберіть вигляд" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="list">Список</SelectItem>
            <SelectItem value="kanban">Канбан</SelectItem>
            <SelectItem value="calendar">Календар</SelectItem>
            <SelectItem value="tree">Дерево</SelectItem>
          </SelectContent>
        </Select>
      </FormField>
    </section>

    <Separator class="my-6" />

    <!-- Пошук (Search) -->
    <section>
      <h3 class="mb-4 text-lg font-semibold text-foreground">Пошук</h3>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Поля пошуку</Label>

        <div v-if="searchFields.length" class="mb-2 flex flex-wrap gap-2">
          <Badge v-for="sf in searchFields" :key="sf" variant="secondary" class="flex items-center gap-1">
            {{ sf }}
            <Button variant="ghost" size="icon" class="h-4 w-4 p-0 hover:bg-transparent" @click="removeSearchField(sf)">
              <X class="h-3 w-3" />
            </Button>
          </Badge>
        </div>

        <Select :model-value="searchFieldSelect" @update:model-value="addSearchField($event as string)">
          <SelectTrigger>
            <SelectValue placeholder="Додати поле для пошуку" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="field in availableSearchFields" :key="field.fieldname" :value="field.fieldname">
              {{ field.label || field.fieldname }}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>
    </section>
  </div>
</template>
