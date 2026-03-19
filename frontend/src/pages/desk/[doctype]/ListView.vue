<template>
  <div class="py-6 px-8 max-w-7xl mx-auto">
    <div class="sm:flex sm:items-center">
      <div class="sm:flex-auto">
        <h1 class="text-2xl font-semibold text-gray-900">Список: {{ route.params.doctype }}</h1>
      </div>
      <div class="mt-4 sm:ml-16 sm:mt-0 sm:flex-none">
        <router-link :to="`/desk/${route.params.doctype}/new`" class="block rounded-md bg-primary-700 px-3 py-2 text-center text-sm font-semibold text-white shadow-sm hover:bg-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-700">
          Створити
        </router-link>
      </div>
    </div>
    
    <div class="mt-8" v-if="isLoading">Завантаження...</div>
    <div class="mt-8" v-else-if="error">Помилка завантаження даних.</div>
    <div class="mt-8 flow-root" v-else>
      <div class="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
        <div class="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8">
          <div class="overflow-hidden shadow ring-1 ring-black ring-opacity-5 sm:rounded-lg">
            <template v-if="data?.data && data.data.length > 0">
              <table class="min-w-full divide-y divide-gray-300">
                <thead class="bg-gray-50">
                  <tr>
                    <th scope="col" class="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-6">Назва / ID</th>
                    <th scope="col" class="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">Створено</th>
                    <th scope="col" class="relative py-3.5 pl-3 pr-4 sm:pr-6">
                      <span class="sr-only">Дії</span>
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 bg-white">
                  <tr v-for="item in data?.data" :key="item.id">
                    <td class="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-6">{{ item.name || item.id }}</td>
                    <td class="whitespace-nowrap px-3 py-4 text-sm text-gray-500">{{ new Date(item.created_at).toLocaleString() }}</td>
                    <td class="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-6">
                      <router-link :to="`/desk/${route.params.doctype}/${item.id}`" class="text-primary-600 hover:text-primary-900">Відкрити<span class="sr-only">, {{ item.id }}</span></router-link>
                    </td>
                  </tr>
                </tbody>
              </table>
            </template>
            <div v-else class="p-8 text-center text-gray-500 bg-white">
              Документи не знайдено
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { api } from '../../../core/api'

const route = useRoute()
const doctype = computed(() => route.params.doctype as string)

const { data, isLoading, error } = useQuery({
  queryKey: ['docList', doctype],
  queryFn: () => api.docs.getList(doctype.value)
})
</script>
