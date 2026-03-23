<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FormField } from '@/components/ui/form-field'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import { Loader2 } from 'lucide-vue-next'

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
      <Button @click="showNewModal = true">+ Новий DocType</Button>
    </div>

    <div v-if="isLoading" class="flex justify-center py-16">
      <Spinner size="lg" />
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
        <Button size="sm" variant="secondary" @click="router.push(`/studio/${dt.name}/builder`)">Редагувати форму</Button>
      </div>
    </div>

    <Dialog :open="showNewModal" @update:open="showNewModal = $event">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новий DocType</DialogTitle>
        </DialogHeader>
        <div class="flex flex-col gap-4">
          <FormField label="Назва (PascalCase)" required :error="nameError">
            <template #default="{ id }">
              <Input :id="id" v-model="newForm.name" placeholder="MyModel" />
            </template>
          </FormField>
          <FormField label="Label (для відображення)">
            <template #default="{ id }">
              <Input :id="id" v-model="newForm.label" :placeholder="newForm.name || 'My Model'" />
            </template>
          </FormField>
          <FormField label="Модуль">
            <template #default="{ id }">
              <Input :id="id" v-model="newForm.module" placeholder="core" />
            </template>
          </FormField>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="newForm.is_child" type="checkbox" class="rounded" />
            <span class="text-sm text-[--grunt-text-primary]">Child DocType (для Table поля)</span>
          </label>
        </div>
        <DialogFooter>
          <Button variant="secondary" @click="showNewModal = false">Скасувати</Button>
          <Button :disabled="isSaving" @click="createDocType"><Loader2 v-if="isSaving" class="size-4 animate-spin" />Створити</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
