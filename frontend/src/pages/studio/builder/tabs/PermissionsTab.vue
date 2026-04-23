<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { Trash2 } from '@lucide/vue'
import client from '@/core/api/client'

const physicalFieldTypes = new Set([
  'Text', 'LongText', 'Int', 'Float', 'Check', 'Date', 'Datetime',
  'Time', 'Link', 'MultiLink', 'Attach', 'Image', 'Select',
  'RichText', 'JSON', 'Code', 'Color', 'Geolocation', 'Signature',
])

const availableFields = computed(() =>
  (builder.doctype?.fields ?? [])
    .filter(f => physicalFieldTypes.has(f.fieldtype))
    .map(f => ({ value: f.fieldname, label: f.label || f.fieldname }))
)

const builder = useBuilderStore()

const availableRoles = ref<string[]>([])
const newRole = ref('')

onMounted(async () => {
  try {
    const { data } = await client.get('/api/v1/auth/roles')
    availableRoles.value = (data.data ?? []).map((r: { name: string }) => r.name)
  } catch {
    availableRoles.value = ['Administrator', 'All']
  }
})

const permissions = computed(() => builder.doctype?.permissions ?? [])

const unusedRoles = computed(() => {
  const used = new Set(permissions.value.map((p) => p.role))
  return availableRoles.value.filter((r) => !used.has(r))
})

function addRole() {
  if (!newRole.value) return
  builder.addPermission(newRole.value)
  newRole.value = ''
}
</script>

<template>
  <div class="max-w-4xl mx-auto p-6">
    <div class="mb-6">
      <h2 class="text-lg font-semibold tracking-tight">Права доступу</h2>
      <p class="text-sm text-muted-foreground">
        Налаштуйте дозволи для кожної ролі
      </p>
    </div>

    <template v-if="permissions.length > 0">
      <DataTable :value="permissions" size="small" stripedRows class="border border-border/50 rounded-lg overflow-hidden">
        <Column field="role" header="Роль" class="font-medium" />
        
        <Column header="Читати" class="text-center" headerClass="justify-center">
          <template #body="{ index }">
            <Checkbox binary
              :model-value="!!permissions[index].read"
              @update:model-value="builder.updatePermission(index, { read: $event })"
            />
          </template>
        </Column>

        <Column header="Писати" class="text-center" headerClass="justify-center">
          <template #body="{ index }">
            <Checkbox binary
              :model-value="!!permissions[index].write"
              @update:model-value="builder.updatePermission(index, { write: $event })"
            />
          </template>
        </Column>

        <Column header="Створити" class="text-center" headerClass="justify-center">
          <template #body="{ index }">
            <Checkbox binary
              :model-value="!!permissions[index].create"
              @update:model-value="builder.updatePermission(index, { create: $event })"
            />
          </template>
        </Column>

        <Column header="Видалити" class="text-center" headerClass="justify-center">
          <template #body="{ index }">
            <Checkbox binary
              :model-value="!!permissions[index].delete"
              @update:model-value="builder.updatePermission(index, { delete: $event })"
            />
          </template>
        </Column>

        <Column v-if="builder.doctype?.is_submittable" header="Підтвердити" class="text-center" headerClass="justify-center">
          <template #body="{ index }">
            <Checkbox binary
              :model-value="!!permissions[index].submit"
              @update:model-value="builder.updatePermission(index, { submit: $event })"
            />
          </template>
        </Column>

        <Column header="Звіти" class="text-center" headerClass="justify-center">
          <template #body="{ index }">
            <Checkbox binary
              :model-value="!!permissions[index].report"
              @update:model-value="builder.updatePermission(index, { report: $event })"
            />
          </template>
        </Column>

        <Column header="Фільтр рядків">
          <template #body="{ data, index }">
            <InputText
              :model-value="data.match ?? ''"
              placeholder="owner == user"
              class="h-8 text-xs w-40"
              @update:model-value="builder.updatePermission(index, { match: String($event) || null })"
            />
          </template>
        </Column>

        <Column header="Приховані поля">
          <template #body="{ data, index }">
            <div class="flex flex-wrap gap-1 max-w-[220px]">
              <template v-if="availableFields.length">
                <MultiSelect
                  :model-value="data.hidden_fields ?? []"
                  :options="availableFields"
                  optionLabel="label"
                  optionValue="value"
                  placeholder="Всі видимі"
                  :maxSelectedLabels="1"
                  selectedItemsLabel="{0} приховано"
                  class="w-full md:w-40 text-xs h-8"
                  @update:model-value="builder.updatePermission(index, { hidden_fields: $event })"
                />
              </template>
              <span v-else class="text-xs text-muted-foreground">—</span>
            </div>
          </template>
        </Column>

        <Column class="w-12">
          <template #body="{ index }">
            <Button text severity="danger" size="small"
              @click="builder.removePermission(index)"
            >
              <Trash2 class="size-4" />
            </Button>
          </template>
        </Column>
      </DataTable>
    </template>

    <div
      v-else
      class="text-center text-sm text-muted-foreground py-12"
    >
      Немає налаштованих прав. Додайте роль для початку.
    </div>

    <div class="flex items-center gap-2 mt-4">
      <Select
        v-model="newRole"
        :options="unusedRoles"
        placeholder="Оберіть роль"
        class="w-60"
      />
      <Button :disabled="!newRole" @click="addRole">Додати</Button>
    </div>
  </div>
</template>
