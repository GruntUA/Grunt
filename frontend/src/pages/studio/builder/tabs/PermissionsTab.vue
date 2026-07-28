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
      <Table class="border border-border/50 rounded-lg overflow-hidden">
        <TableHeader>
          <TableRow>
            <TableHead class="font-medium">Роль</TableHead>
            <TableHead class="text-center">Читати</TableHead>
            <TableHead class="text-center">Писати</TableHead>
            <TableHead class="text-center">Створити</TableHead>
            <TableHead class="text-center">Видалити</TableHead>
            <TableHead v-if="builder.doctype?.is_submittable" class="text-center">Підтвердити</TableHead>
            <TableHead class="text-center">Звіти</TableHead>
            <TableHead>Фільтр рядків</TableHead>
            <TableHead>Приховані поля</TableHead>
            <TableHead class="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="(perm, index) in permissions" :key="index" class="odd:bg-muted/20">
            <TableCell class="font-medium">{{ perm.role }}</TableCell>

            <TableCell class="text-center">
              <Checkbox
                :model-value="!!perm.read"
                @update:model-value="builder.updatePermission(index, { read: $event })"
              />
            </TableCell>

            <TableCell class="text-center">
              <Checkbox
                :model-value="!!perm.write"
                @update:model-value="builder.updatePermission(index, { write: $event })"
              />
            </TableCell>

            <TableCell class="text-center">
              <Checkbox
                :model-value="!!perm.create"
                @update:model-value="builder.updatePermission(index, { create: $event })"
              />
            </TableCell>

            <TableCell class="text-center">
              <Checkbox
                :model-value="!!perm.delete"
                @update:model-value="builder.updatePermission(index, { delete: $event })"
              />
            </TableCell>

            <TableCell v-if="builder.doctype?.is_submittable" class="text-center">
              <Checkbox
                :model-value="!!perm.submit"
                @update:model-value="builder.updatePermission(index, { submit: $event })"
              />
            </TableCell>

            <TableCell class="text-center">
              <Checkbox
                :model-value="!!perm.report"
                @update:model-value="builder.updatePermission(index, { report: $event })"
              />
            </TableCell>

            <TableCell>
              <Input
                :model-value="perm.match ?? ''"
                placeholder="owner == user"
                class="h-8 text-xs w-40"
                @update:model-value="builder.updatePermission(index, { match: String($event) || null })"
              />
            </TableCell>

            <TableCell>
              <div class="flex flex-wrap gap-1 max-w-[220px]">
                <template v-if="availableFields.length">
                  <MultiSelect
                    :model-value="perm.hidden_fields ?? []"
                    :options="availableFields"
                    option-label="label"
                    option-value="value"
                    placeholder="Всі видимі"
                    class="w-full md:w-40 text-xs h-8"
                    @update:model-value="builder.updatePermission(index, { hidden_fields: $event })"
                  />
                </template>
                <span v-else class="text-xs text-muted-foreground">—</span>
              </div>
            </TableCell>

            <TableCell class="w-12">
              <Button variant="ghost" size="sm" class="text-destructive hover:text-destructive"
                @click="builder.removePermission(index)"
              >
                <Trash2 class="size-4" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </template>

    <div
      v-else
      class="text-center text-sm text-muted-foreground py-12"
    >
      Немає налаштованих прав. Додайте роль для початку.
    </div>

    <div class="flex items-center gap-2 mt-4">
      <Select v-model="newRole">
        <SelectTrigger class="w-60">
          <SelectValue placeholder="Оберіть роль" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in unusedRoles" :key="opt" :value="opt">{{ opt }}</SelectItem>
        </SelectContent>
      </Select>
      <Button :disabled="!newRole" @click="addRole">Додати</Button>
    </div>
  </div>
</template>
