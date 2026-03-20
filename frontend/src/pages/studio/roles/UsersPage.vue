<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { authAdminApi } from '@/core/api/auth-admin'
import type { GruntUserPublic } from '@/types'
import GButton from '@/components/ui/GButton.vue'
import GSpinner from '@/components/ui/GSpinner.vue'

const users = ref<GruntUserPublic[]>([])
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
      <h1 class="text-xl font-semibold text-[--grunt-text-primary]">Користувачі</h1>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <GSpinner size="lg" />
    </div>

    <div v-else class="flex flex-col gap-4">
      <div
        v-for="user in users"
        :key="user.id"
        class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] p-4"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="font-medium text-[--grunt-text-primary]">{{ user.full_name }}</p>
            <p class="text-sm text-[--grunt-text-secondary]">{{ user.email }}</p>
            <span
              v-if="user.is_superadmin"
              class="inline-block mt-1 text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full"
            >Superadmin</span>
          </div>
          <div class="flex-1">
            <p class="text-xs text-[--grunt-text-muted] mb-1.5">Ролі:</p>
            <div class="flex flex-wrap gap-1.5 mb-3">
              <span
                v-for="role in user.roles"
                :key="role"
                class="inline-flex items-center gap-1 text-xs bg-[--grunt-primary-light] text-[--grunt-primary] px-2 py-0.5 rounded-full"
              >
                {{ role }}
                <button class="hover:text-[--grunt-danger] font-bold" @click="removeRole(user.id, role)">&times;</button>
              </span>
              <span v-if="user.roles.length === 0" class="text-xs text-[--grunt-text-muted]">Немає ролей</span>
            </div>
            <!-- Add role form for this user -->
            <div v-if="selectedUserId === user.id" class="flex gap-2">
              <input
                v-model="newRole"
                type="text"
                placeholder="Назва ролі"
                class="text-sm border border-[--grunt-border] rounded-[--grunt-radius-sm] px-2 py-1 focus:outline-none focus:border-[--grunt-primary]"
                @keydown.enter="addRole(user.id)"
              />
              <GButton size="sm" :loading="isSubmitting" @click="addRole(user.id)">Додати</GButton>
              <GButton size="sm" variant="ghost" @click="selectedUserId = ''">Скасувати</GButton>
            </div>
            <GButton
              v-else
              size="sm"
              variant="ghost"
              @click="selectedUserId = user.id; newRole = ''"
            >+ Роль</GButton>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
