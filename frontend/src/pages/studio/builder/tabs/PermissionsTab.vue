<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import Select from 'primevue/select'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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

function toggleHiddenField(permIndex: number, fieldname: string) {
  const perm = permissions.value[permIndex]
  const current: string[] = perm.hidden_fields ?? []
  const next = current.includes(fieldname)
    ? current.filter(f => f !== fieldname)
    : [...current, fieldname]
  builder.updatePermission(permIndex, { hidden_fields: next })
}

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
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Роль</TableHead>
            <TableHead class="text-center">Читати</TableHead>
            <TableHead class="text-center">Писати</TableHead>
            <TableHead class="text-center">Створити</TableHead>
            <TableHead class="text-center">Видалити</TableHead>
            <TableHead
              v-if="builder.doctype?.is_submittable"
              class="text-center"
            >
              Підтвердити
            </TableHead>
            <TableHead class="text-center">Звіти</TableHead>
            <TableHead>Фільтр рядків</TableHead>
            <TableHead>Приховані поля</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="(perm, i) in permissions" :key="i">
            <TableCell class="font-medium">{{ perm.role }}</TableCell>
            <TableCell class="text-center">
              <Checkbox
                :checked="!!perm.read"
                @update:checked="builder.updatePermission(i, { read: $event })"
              />
            </TableCell>
            <TableCell class="text-center">
              <Checkbox
                :checked="!!perm.write"
                @update:checked="builder.updatePermission(i, { write: $event })"
              />
            </TableCell>
            <TableCell class="text-center">
              <Checkbox
                :checked="!!perm.create"
                @update:checked="builder.updatePermission(i, { create: $event })"
              />
            </TableCell>
            <TableCell class="text-center">
              <Checkbox
                :checked="!!perm.delete"
                @update:checked="builder.updatePermission(i, { delete: $event })"
              />
            </TableCell>
            <TableCell
              v-if="builder.doctype?.is_submittable"
              class="text-center"
            >
              <Checkbox
                :checked="!!perm.submit"
                @update:checked="builder.updatePermission(i, { submit: $event })"
              />
            </TableCell>
            <TableCell class="text-center">
              <Checkbox
                :checked="!!perm.report"
                @update:checked="builder.updatePermission(i, { report: $event })"
              />
            </TableCell>
            <TableCell>
              <Input
                :model-value="perm.match ?? ''"
                placeholder="owner == user"
                class="h-8 text-xs w-40"
                @update:model-value="builder.updatePermission(i, { match: String($event) || null })"
              />
            </TableCell>
            <TableCell>
              <div class="flex flex-wrap gap-1 max-w-[220px]">
                <template v-if="availableFields.length">
                  <DropdownMenu>
                    <DropdownMenuTrigger as-child>
                      <Button variant="outline" size="sm" class="h-7 text-xs">
                        {{ (perm.hidden_fields ?? []).length
                            ? `${(perm.hidden_fields ?? []).length} приховано`
                            : 'Всі видимі' }}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent class="w-56 max-h-64 overflow-y-auto">
                      <DropdownMenuLabel class="text-xs">Приховати поле для цієї ролі</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      <DropdownMenuCheckboxItem
                        v-for="field in availableFields"
                        :key="field.value"
                        :checked="(perm.hidden_fields ?? []).includes(field.value)"
                        @update:checked="toggleHiddenField(i, field.value)"
                      >
                        {{ field.label }}
                      </DropdownMenuCheckboxItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </template>
                <span v-else class="text-xs text-muted-foreground">—</span>
              </div>
            </TableCell>
            <TableCell>
              <Button
                variant="ghost"
                size="icon-sm"
                @click="builder.removePermission(i)"
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
