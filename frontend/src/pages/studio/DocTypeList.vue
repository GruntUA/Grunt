<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import GButton from '@/components/ui/GButton.vue'
import GInput from '@/components/ui/GInput.vue'
import GModal from '@/components/ui/GModal.vue'
import GSpinner from '@/components/ui/GSpinner.vue'

const router = useRouter()
const doctypes = ref<DocTypeSummary[]>([])
const isLoading = ref(true)
const showNewModal = ref(false)
const isSaving = ref(false)

const newForm = ref({ name: '', label: '', module: '', is_child: false })
const nameError = ref('')

onMounted(async () => {
  try { doctypes.value = await metaApi.list() }
  finally { isLoading.value = false }
})

function validateName(v: string): boolean {
  return /^[A-Z][a-zA-Z0-9]*$/.test(v)
}

async function createDocType() {
  nameError.value = ''
  if (!validateName(newForm.value.name)) {
    nameError.value = 'Назва має бути PascalCase, наприклад: MyModel'
    return
  }
  if (!newForm.value.label) newForm.value.label = newForm.value.name
  if (!newForm.value.module) newForm.value.module = 'core'
  isSaving.value = true
  try {
    await metaApi.create({ ...newForm.value, fields: [] })
    showNewModal.value = false
    router.push(`/studio/${newForm.value.name}/builder`)
  } catch {
    nameError.value = 'Помилка створення. Можливо такий DocType вже існує.'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="p-8">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold text-[--grunt-text-primary]">App Studio</h1>
        <p class="text-sm text-[--grunt-text-secondary] mt-1">Конструктор DocTypes і форм</p>
      </div>
      <GButton @click="showNewModal = true">+ Новий DocType</GButton>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <GSpinner size="lg" />
    </div>

    <div v-else-if="!doctypes.length" class="text-center py-16 text-[--grunt-text-muted]">
      <p class="text-4xl mb-3">📋</p>
      <p>Ще немає DocTypes. Створіть перший!</p>
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="dt in doctypes"
        :key="dt.name"
        class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 hover:border-[--grunt-primary] hover:shadow-sm transition-all"
      >
        <div class="flex items-start justify-between mb-3">
          <div>
            <p class="font-semibold text-[--grunt-text-primary]">{{ dt.label }}</p>
            <p class="text-xs text-[--grunt-text-muted] mt-0.5">{{ dt.name }}</p>
          </div>
          <span class="text-xs px-2 py-0.5 bg-[--grunt-surface-secondary] rounded text-[--grunt-text-secondary]">{{ dt.module }}</span>
        </div>
        <p class="text-sm text-[--grunt-text-secondary] mb-4">{{ dt.module }}</p>
        <GButton size="sm" variant="secondary" @click="router.push(`/studio/${dt.name}/builder`)">Редагувати форму</GButton>
      </div>
    </div>

    <GModal v-model="showNewModal" title="Новий DocType">
      <div class="flex flex-col gap-4">
        <GInput
          v-model="newForm.name"
          label="Назва (PascalCase)"
          placeholder="MyModel"
          :error="nameError"
          required
        />
        <GInput v-model="newForm.label" label="Label (для відображення)" :placeholder="newForm.name || 'My Model'" />
        <GInput v-model="newForm.module" label="Модуль" placeholder="core" />
        <label class="flex items-center gap-2 cursor-pointer">
          <input v-model="newForm.is_child" type="checkbox" class="rounded" />
          <span class="text-sm text-[--grunt-text-primary]">Child DocType (для Table поля)</span>
        </label>
      </div>
      <template #footer>
        <GButton variant="secondary" @click="showNewModal = false">Скасувати</GButton>
        <GButton :loading="isSaving" @click="createDocType">Створити</GButton>
      </template>
    </GModal>
  </div>
</template>
