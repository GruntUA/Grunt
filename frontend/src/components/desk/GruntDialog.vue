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

watch(() => state.open, (v) => {
  if (v && state.type === 'prompt' && state.fields.length > 0) {
    promptValue.value = String(state.fields[0].default ?? '')
  }
})

function onConfirm() {
  if (state.type === 'confirm') close(true)
  else if (state.type === 'prompt') close(promptValue.value || null)
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
      <!-- Msgprint -->
      <template v-if="state.type === 'msgprint'">
        <DialogHeader>
          <DialogTitle v-if="state.title">
            <span v-if="state.indicator" class="inline-block w-2.5 h-2.5 rounded-full mr-2" :style="{ backgroundColor: state.indicator }" />
            {{ state.title }}
          </DialogTitle>
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
        </DialogHeader>
        <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
          <Label :for="field.fieldname">{{ field.label }}</Label>
          <Input
            :id="field.fieldname"
            v-model="promptValue"
            :placeholder="field.placeholder"
            :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
            @keydown.enter="onConfirm"
          />
        </div>
        <DialogFooter class="gap-2">
          <Button variant="outline" @click="onCancel">Скасувати</Button>
          <Button @click="onConfirm">OK</Button>
        </DialogFooter>
      </template>

      <!-- Progress -->
      <template v-if="state.type === 'progress'">
        <DialogHeader>
          <DialogTitle>{{ state.title }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-2">
          <div class="w-full h-2.5 bg-muted rounded-full overflow-hidden">
            <div
              class="h-full bg-primary rounded-full transition-all duration-300"
              :style="{ width: `${state.progress.percent}%` }"
            />
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
