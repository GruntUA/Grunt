<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDialog } from '@/core/composables/useDialog'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const { state, close } = useDialog()
const promptValue = ref('')
const formValues = ref<Record<string, any>>({})

watch(() => state.open, (v) => {
  if (v) {
    if (state.type === 'prompt' && state.fields.length > 0) {
      promptValue.value = String(state.fields[0].default ?? '')
    } else if (state.type === 'dialog') {
      const vals: Record<string, any> = {}
      state.fields.forEach(f => {
        vals[f.fieldname] = f.default ?? (f.fieldtype === 'Check' ? false : '')
      })
      formValues.value = vals
    }
  }
})

function onConfirm() {
  if (state.type === 'confirm') close(true)
  else if (state.type === 'prompt') close(promptValue.value || null)
  else if (state.type === 'dialog') close({ ...formValues.value })
  else close()
}

function onCancel() {
  if (state.type === 'confirm') close(false)
  else if (state.type === 'prompt') close(null)
  else close()
}

function onOpenChange(v: boolean) {
  if (!v) onCancel()
}
</script>

<template>
  <Dialog :open="state.open" @update:open="onOpenChange">
    <DialogContent class="sm:max-w-md">
      <!-- Hidden titles for accessibility if not provided -->
      <DialogHeader v-if="!state.title" class="sr-only">
        <DialogTitle>Dialog</DialogTitle>
        <DialogDescription>Action dialog</DialogDescription>
      </DialogHeader>

      <!-- Msgprint -->
      <template v-if="state.type === 'msgprint'">
        <DialogHeader>
          <DialogTitle v-if="state.title">
            <span v-if="state.indicator" class="inline-block w-2.5 h-2.5 rounded-full mr-2"
              :style="{ backgroundColor: state.indicator }" />
            {{ state.title }}
          </DialogTitle>
          <DialogDescription class="sr-only">Message from system</DialogDescription>
        </DialogHeader>
        <div class="text-sm text-foreground leading-relaxed whitespace-pre-wrap" v-html="state.message" />
        <DialogFooter>
          <Button @click="close()">OK</Button>
        </DialogFooter>
      </template>

      <!-- Confirm -->
      <template v-if="state.type === 'confirm'">
        <DialogHeader>
          <DialogTitle>{{ state.title }}</DialogTitle>
        </DialogHeader>
        <DialogDescription class="text-sm text-muted-foreground">
          {{ state.message }}
        </DialogDescription>
        <DialogFooter class="gap-2">
          <Button variant="outline" @click="onCancel">Скасувати</Button>
          <Button @click="onConfirm">Підтвердити</Button>
        </DialogFooter>
      </template>

      <!-- Prompt -->
      <template v-if="state.type === 'prompt'">
        <DialogHeader>
          <DialogTitle v-if="state.title">{{ state.title }}</DialogTitle>
          <DialogDescription class="sr-only">Введіть дані</DialogDescription>
        </DialogHeader>
        <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
          <Label :for="field.fieldname">{{ field.label }}</Label>
          <div v-if="field.fieldtype === 'HTML'" v-html="field.default" class="rounded border p-2 bg-muted/30" />
          <Input v-else :id="field.fieldname" v-model="promptValue" :placeholder="field.placeholder"
            :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
            @keydown.enter="onConfirm" />
        </div>
        <DialogFooter class="gap-2">
          <Button variant="outline" @click="onCancel">Скасувати</Button>
          <Button @click="onConfirm">OK</Button>
        </DialogFooter>
      </template>

      <!-- Custom Dialog (grunt.form) -->
      <template v-if="state.type === 'dialog'">
        <DialogHeader>
          <DialogTitle v-if="state.title">{{ state.title }}</DialogTitle>
          <DialogDescription class="sr-only">Заповніть форму</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
            <template v-if="field.fieldtype === 'HTML'">
              <Label v-if="field.label" class="mb-1 block text-sm font-medium">{{ field.label }}</Label>
              <div v-html="String(field.default || '').replace(/<\?xml.*\?>/g, '')"
                class="rounded-lg border-2 border-dashed p-6 flex justify-center bg-white shadow-inner min-h-[240px] items-center [&>svg]:block [&>svg]:max-w-full [&>svg]:h-auto" />
            </template>
            <template v-else-if="field.fieldtype === 'Check'">
              <div class="flex items-center space-x-2 py-1">
                <input type="checkbox" :id="field.fieldname" v-model="formValues[field.fieldname]"
                  class="size-4 rounded border-gray-300 text-primary focus:ring-primary" />
                <Label :for="field.fieldname" class="cursor-pointer">{{ field.label }}</Label>
              </div>
            </template>
            <template v-else>
              <Label :for="field.fieldname">{{ field.label }}</Label>
              <Input :id="field.fieldname" v-model="formValues[field.fieldname]" :placeholder="field.placeholder"
                :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
                @keydown.enter="onConfirm" />
            </template>
          </div>
        </div>
        <DialogFooter class="gap-2">
          <Button variant="outline" @click="onCancel">Скасувати</Button>
          <Button @click="onConfirm">{{ state.primaryLabel }}</Button>
        </DialogFooter>
      </template>

      <!-- Progress -->
      <template v-if="state.type === 'progress'">
        <DialogHeader>
          <DialogTitle>{{ state.title }}</DialogTitle>
          <DialogDescription class="sr-only">Завантаження...</DialogDescription>
        </DialogHeader>
        <div class="space-y-2">
          <div class="w-full h-2.5 bg-muted rounded-full overflow-hidden">
            <div class="h-full bg-primary rounded-full transition-all duration-300"
              :style="{ width: `${state.progress.percent}%` }" />
          </div>
          <div class="flex items-center justify-between text-xs text-muted-foreground">
            <span v-if="state.progress.description">{{ state.progress.description }}</span>
            <span class="tabular-nums ml-auto">{{ state.progress.percent }}%</span>
          </div>
        </div>
      </template>
    </DialogContent>
  </Dialog>
</template>
