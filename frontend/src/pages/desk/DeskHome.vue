<template>
  <div class="h-screen flex overflow-hidden bg-gray-50">
    <!-- Sidebar -->
    <div class="flex flex-col w-64 border-r border-gray-200 bg-white">
      <div class="flex h-16 items-center flex-shrink-0 px-4 bg-primary-700 text-white">
        <h1 class="text-xl font-bold">Ґрунт</h1>
      </div>
      <div class="flex flex-col flex-grow overflow-y-auto">
        <nav class="flex-1 px-2 py-4 space-y-1">
          <router-link 
            v-for="item in docTypes" 
            :key="item.name"
            :to="`/desk/${item.name}`"
            class="group flex items-center px-2 py-2 text-sm font-medium rounded-md text-gray-700 hover:bg-gray-100 hover:text-primary-700"
            active-class="bg-gray-100 text-primary-700"
          >
            {{ item.label }}
          </router-link>
        </nav>
      </div>
      <div class="flex-shrink-0 flex border-t border-gray-200 p-4">
        <button @click="logout" class="text-sm font-medium text-gray-700 hover:text-gray-900">
          Вийти
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div class="flex flex-col flex-1 overflow-hidden">
      <main class="flex-1 relative overflow-y-auto focus:outline-none">
        <router-view :key="$route.path" />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useDocTypeStore } from '../../stores/doctype'

const router = useRouter()
const authStore = useAuthStore()
const docStore = useDocTypeStore()

// If no doctypes are cached, fetch them
if (!docStore.docTypes) {
  docStore.refetch()
}

const docTypes = computed(() => docStore.docTypes || [])

const logout = () => {
  authStore.logout()
  router.push('/login')
}
</script>
