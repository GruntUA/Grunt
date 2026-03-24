<script setup lang="ts">
import { computed, ref } from 'vue'
import { useBuilderStore } from '@/stores/builder'
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

// --- Computed helpers ---

const dataFields = computed(() =>
  (builder.doctype?.fields ?? []).filter(
    (f) => !['Section', 'Column', 'Tab', 'Table'].includes(f.fieldtype),
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
        <Input
          :model-value="builder.doctype?.label ?? ''"
          @update:model-value="builder.updateDocType({ label: String($event) })"
        />
      </FormField>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Модуль</Label>
        <Input
          :model-value="builder.doctype?.module ?? ''"
          @update:model-value="builder.updateDocType({ module: String($event) })"
        />
      </FormField>

      <div class="grid grid-cols-2 gap-4">
        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Сінглтон</Label>
          <Switch
            :checked="!!builder.doctype?.is_singleton"
            @update:checked="builder.updateDocType({ is_singleton: $event })"
          />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Подання</Label>
          <Switch
            :checked="!!builder.doctype?.is_submittable"
            @update:checked="builder.updateDocType({ is_submittable: $event })"
          />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Дочірній</Label>
          <Switch
            :checked="!!builder.doctype?.is_child"
            @update:checked="builder.updateDocType({ is_child: $event })"
          />
        </div>

        <div class="flex items-center justify-between rounded-md border border-border p-3">
          <Label class="text-sm text-foreground">Відстеження змін</Label>
          <Switch
            :checked="!!builder.doctype?.track_changes"
            @update:checked="builder.updateDocType({ track_changes: $event })"
          />
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
            <SelectItem
              v-for="field in dataFields"
              :key="field.fieldname"
              :value="field.fieldname"
            >
              {{ field.label || field.fieldname }}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>

      <FormField v-if="autonameStrategy === 'format:'" class="mb-4">
        <Label class="text-muted-foreground">Шаблон</Label>
        <Input
          :model-value="autonameValue"
          placeholder="CONTR-.YYYY.-.####"
          @update:model-value="setAutonameValue($event as any)"
        />
      </FormField>

      <FormField class="mb-4">
        <Label class="text-muted-foreground">Поле заголовка</Label>
        <Select
          :model-value="builder.doctype?.title_field || '__name__'"
          @update:model-value="builder.updateDocType({ title_field: String($event) === '__name__' ? undefined : String($event) })"
        >
          <SelectTrigger>
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__name__">name</SelectItem>
            <SelectItem
              v-for="field in dataFields"
              :key="field.fieldname"
              :value="field.fieldname"
            >
              {{ field.label || field.fieldname }}
            </SelectItem>
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
          <Badge
            v-for="sf in searchFields"
            :key="sf"
            variant="secondary"
            class="flex items-center gap-1"
          >
            {{ sf }}
            <Button
              variant="ghost"
              size="icon"
              class="h-4 w-4 p-0 hover:bg-transparent"
              @click="removeSearchField(sf)"
            >
              <X class="h-3 w-3" />
            </Button>
          </Badge>
        </div>

        <Select
          :model-value="searchFieldSelect"
          @update:model-value="addSearchField($event as string)"
        >
          <SelectTrigger>
            <SelectValue placeholder="Додати поле для пошуку" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="field in availableSearchFields"
              :key="field.fieldname"
              :value="field.fieldname"
            >
              {{ field.label || field.fieldname }}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>
    </section>
  </div>
</template>
