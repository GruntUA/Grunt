<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { authAdminApi } from '@/core/api/auth-admin'
import type { UserPublic } from '@/types'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Loader2 } from '@lucide/vue'

const users = ref<UserPublic[]>([])
const isLoading = ref(true)
const newRole = ref('')
const selectedUserId = ref('')
const isSubmitting = ref(false)

async function loadUsers() {
  isLoading.value = true
  try {
    users.value = await authAdminApi.listUsers()
  } finally {
    isLoading.value = false
  }
}

async function addRole(userId: string) {
  const role = newRole.value.trim()
  if (!role) return
  isSubmitting.value = true
  try {
    await authAdminApi.addRole(userId, role)
    newRole.value = ''
    selectedUserId.value = ''
    await loadUsers()
  } finally {
    isSubmitting.value = false
  }
}

async function removeRole(userId: string, role: string) {
  try {
    await authAdminApi.removeRole(userId, role)
    await loadUsers()
  } catch {
    // silent
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="p-8 max-w-5xl">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-foreground">Користувачі</h1>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <Spinner size="lg" />
    </div>

    <div v-else class="flex flex-col gap-4">
      <div v-for="user in users" :key="user.id" class="bg-card border border-border rounded-md p-4">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="font-medium text-foreground">{{ user.full_name }}</p>
            <p class="text-sm text-muted-foreground">{{ user.email }}</p>
            <span v-if="user.is_superadmin"
              class="inline-block mt-1 text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full">Superadmin</span>
          </div>
          <div class="flex-1">
            <p class="text-xs text-muted-foreground/70 mb-1.5">Ролі:</p>
            <div class="flex flex-wrap gap-1.5 mb-3">
              <span v-for="role in user.roles" :key="role"
                class="inline-flex items-center gap-1 text-xs bg-accent text-primary px-2 py-0.5 rounded-full">
                {{ role }}
                <button class="hover:text-destructive font-bold" @click="removeRole(user.id, role)">&times;</button>
              </span>
              <span v-if="user.roles.length === 0" class="text-xs text-muted-foreground/70">Немає ролей</span>
            </div>
            <!-- Add role form for this user -->
            <div v-if="selectedUserId === user.id" class="flex gap-2">
              <input v-model="newRole" type="text" placeholder="Назва ролі"
                class="text-sm border border-border rounded-sm px-2 py-1 focus:outline-none focus:border-primary"
                @keydown.enter="addRole(user.id)" />
              <Button size="sm" :disabled="isSubmitting" @click="addRole(user.id)">
                <Loader2 v-if="isSubmitting" class="size-4 animate-spin" />Додати
              </Button>
              <Button size="sm" variant="ghost" @click="selectedUserId = ''">Скасувати</Button>
            </div>
            <Button v-else size="sm" variant="ghost" @click="selectedUserId = user.id; newRole = ''">+ Роль</Button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
