<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { authAdminApi } from '@/core/api/auth-admin'
import { useDocTypeStore } from '@/stores/doctype'
import { Spinner } from '@/components/ui/spinner'
import { Loader2 } from '@lucide/vue'

interface RoleInfo {
  name: string
  description?: string
}

const roles = ref<RoleInfo[]>([])
const isLoading = ref(true)
const newRoleName = ref('')
const isCreating = ref(false)

const dtStore = useDocTypeStore()

async function loadRoles() {
  isLoading.value = true
  try {
    const r = await authAdminApi.listRoles()
    roles.value = r.data ?? []
  } finally {
    isLoading.value = false
  }
}

async function createRole() {
  const name = newRoleName.value.trim()
  if (!name) return
  isCreating.value = true
  try {
    await authAdminApi.createRole(name)
    newRoleName.value = ''
    await loadRoles()
  } finally {
    isCreating.value = false
  }
}

onMounted(async () => {
  await dtStore.loadAll()
  await loadRoles()
})
</script>

<template>
  <div class="p-8 max-w-4xl">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-foreground">Ролі</h1>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <Spinner size="lg" />
    </div>

    <div v-else class="flex gap-6">
      <!-- Roles list -->
      <div class="w-56 flex-shrink-0">
        <p class="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wide mb-3">Ролі</p>
        <div class="flex flex-col gap-1 mb-4">
          <div
            v-for="role in roles"
            :key="role.name"
            class="px-3 py-2 text-sm rounded-sm bg-card border border-border text-foreground"
          >
            {{ role.name }}
          </div>
          <p v-if="roles.length === 0" class="text-sm text-muted-foreground/70 px-2">Ролей немає</p>
        </div>
        <!-- Create role -->
        <div class="flex flex-col gap-2">
          <input
            v-model="newRoleName"
            type="text"
            placeholder="Нова роль..."
            class="w-full text-sm border border-border rounded-sm px-2 py-1.5 focus:outline-none focus:border-primary"
            @keydown.enter="createRole"
          />
          <Button size="small" :disabled="isCreating" @click="createRole"><Loader2 v-if="isCreating" class="size-4 animate-spin" />Додати роль</Button>
        </div>
      </div>

      <!-- Permissions matrix -->
      <div class="flex-1">
        <p class="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wide mb-3">DocType → Дозволи</p>
        <p class="text-sm text-muted-foreground">
          Налаштування дозволів для конкретних DocType виконується через
          <strong>App Studio &rarr; Builder &rarr; DocType</strong>.
          Дозволи зберігаються у полі <code class="text-xs bg-gray-100 px-1 rounded">permissions</code> DocType.
        </p>
        <div class="mt-4 overflow-x-auto">
          <table class="text-sm border-collapse">
            <thead>
              <tr class="bg-background">
                <th class="px-3 py-2 text-left border border-border font-medium text-muted-foreground">DocType</th>
                <th v-for="role in roles" :key="role.name" class="px-3 py-2 border border-border font-medium text-muted-foreground">{{ role.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="dt in dtStore.doctypes" :key="dt.name" class="hover:bg-muted">
                <td class="px-3 py-2 border border-border text-foreground">{{ dt.label }}</td>
                <td v-for="role in roles" :key="role.name" class="px-3 py-2 border border-border text-center text-muted-foreground/70">
                  —
                </td>
              </tr>
              <tr v-if="dtStore.doctypes.length === 0">
                <td :colspan="roles.length + 1" class="px-3 py-4 text-center text-muted-foreground/70 border border-border">
                  Немає DocTypes
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
