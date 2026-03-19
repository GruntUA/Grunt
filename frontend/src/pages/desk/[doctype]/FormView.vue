<template>
  <div class="py-6 px-8 max-w-4xl mx-auto">
    <div class="mb-6 flex items-center justify-between">
      <div class="flex items-center space-x-4">
        <router-link :to="`/desk/${route.params.doctype}`" class="text-gray-500 hover:text-gray-900">
          &larr; Назад
        </router-link>
        <h1 class="text-2xl font-semibold text-gray-900">
          {{ isNew ? 'Новий документ' : (data?.data?.name || route.params.id) }} 
        </h1>
      </div>
      <div class="flex space-x-3">
        <button v-if="!isNew" @click="handleDelete" class="rounded-md bg-white px-3 py-2 text-sm font-semibold text-red-600 shadow-sm ring-1 ring-inset ring-red-300 hover:bg-gray-50">
          Видалити
        </button>
        <button @click="handleSave" class="rounded-md bg-primary-700 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-600">
          Зберегти
        </button>
      </div>
    </div>

    <div class="bg-white shadow sm:rounded-lg">
      <div class="px-4 py-5 sm:p-6" v-if="isLoading">
        Завантаження структури форми...
      </div>
      <div class="px-4 py-5 sm:p-6" v-else-if="dtError || (docError && !isNew)">
        <div class="text-red-500">Помилка завантаження.</div>
      </div>
      <div class="px-4 py-5 sm:p-6 space-y-6" v-else>
        <!-- Very basic fields generation based on meta -->
        <div v-for="field in fields" :key="field.fieldname" class="sm:col-span-4">
          <label :for="field.fieldname" class="block text-sm font-medium leading-6 text-gray-900">{{ field.label }}<span v-if="field.required" class="text-red-500 ml-1">*</span></label>
          <div class="mt-2 text-gray-500 flex flex-col gap-2">
            <input 
              v-if="['Text', 'Int', 'Float'].includes(field.fieldtype)" 
              :type="field.fieldtype === 'Text' ? 'text' : 'number'" 
              v-model="formData[field.fieldname]" 
              class="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6" 
            />
            <textarea 
              v-else-if="field.fieldtype === 'LongText'" 
              v-model="formData[field.fieldname]"
              rows="3" 
              class="block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6"
            ></textarea>
            <input 
              v-else-if="field.fieldtype === 'Check'" 
              type="checkbox" 
              v-model="formData[field.fieldname]" 
              class="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600" 
            />
            <div v-else class="text-sm italic border rounded p-2 text-orange-600">
              [Тип поля `{{ field.fieldtype }}` ще не підтримується повністю]
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { api } from '../../../core/api'
import { useDocTypeStore } from '../../../stores/doctype'

const route = useRoute()
const router = useRouter()
const dtStore = useDocTypeStore()
const queryClient = useQueryClient()

const doctype = computed(() => route.params.doctype as string)
const docId = computed(() => route.params.id as string)
const isNew = computed(() => docId.value === 'new')

const formData = ref<Record<string, any>>({})

// Load DocType Meta
const { data: dtData, isLoading: dtLoading, error: dtError } = useQuery({
  queryKey: ['doctypeMeta', doctype],
  queryFn: () => dtStore.getDocTypeDetails(doctype.value),
})

const fields = computed(() => {
  return dtData.value?.fields?.filter(f => !['Section', 'Column', 'Tab', 'Table'].includes(f.fieldtype)) || []
})

// Load Document Data if not new
const { data, isLoading: docLoading, error: docError } = useQuery({
  queryKey: ['document', doctype, docId],
  queryFn: () => api.docs.getOne(doctype.value, docId.value),
  enabled: !isNew.value,
})

watch(data, (newData) => {
  if (newData?.data) {
    formData.value = { ...newData.data }
  }
}, { immediate: true })

const isLoading = computed(() => dtLoading.value || (docLoading.value && !isNew.value))

const saveMutation = useMutation({
  mutationFn: (dataToSave: any) => {
    if (isNew.value) {
      return api.docs.create(doctype.value, dataToSave)
    } else {
      return api.docs.update(doctype.value, docId.value, dataToSave)
    }
  },
  onSuccess: (res) => {
    queryClient.invalidateQueries({ queryKey: ['docList', doctype.value] })
    queryClient.invalidateQueries({ queryKey: ['document', doctype.value, docId.value] })
    if (isNew.value) {
      router.replace(`/desk/${doctype.value}/${res.data.id}`)
    }
    alert('Документ збережено!')
  },
  onError: () => {
    alert('Помилка при збереженні')
  }
})

const deleteMutation = useMutation({
  mutationFn: () => api.docs.delete(doctype.value, docId.value),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['docList', doctype.value] })
    router.push(`/desk/${doctype.value}`)
  }
})

const handleSave = () => saveMutation.mutate(formData.value)
const handleDelete = () => {
  if(confirm('Ви впевнені?')) {
    deleteMutation.mutate()
  }
}
</script>
