<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDialog } from '@/core/composables/useDialog'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
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
  <Dialog v-model:visible="state.open" modal
    :pt="{ root: { class: 'sm:max-w-md' }, content: { class: 'p-0 px-6 pb-4 pt-2' } }"
    @hide="onOpenChange(false)">
    <template #header>
      <span v-if="state.title" class="font-semibold flex items-center gap-2">
        <span v-if="state.indicator" class="inline-block w-2.5 h-2.5 rounded-full shrink-0"
          :style="{ backgroundColor: state.indicator }" />
        {{ state.title }}
      </span>
    </template>

    <!-- Content -->
    <div>
        <!-- Msgprint -->
        <div v-if="state.type === 'msgprint'" class="text-sm text-foreground leading-relaxed whitespace-pre-wrap py-2" v-html="state.message" />

        <!-- Confirm -->
        <p v-else-if="state.type === 'confirm'" class="text-sm text-muted-foreground py-2">{{ state.message }}</p>

        <!-- Prompt -->
        <div v-else-if="state.type === 'prompt'" class="space-y-2 py-2">
            <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
                <Label :for="field.fieldname">{{ field.label }}</Label>
                <div v-if="field.fieldtype === 'HTML'" v-html="field.default" class="rounded border p-2 bg-muted/30" />
                <Input v-else :id="field.fieldname" v-model="promptValue" :placeholder="field.placeholder"
                    :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
                    @keydown.enter="onConfirm" />
            </div>
        </div>

        <!-- Custom Dialog (grunt.form) -->
        <div v-else-if="state.type === 'dialog'" class="space-y-4 py-2">
            <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
                <template v-if="field.fieldtype === 'HTML'">
                    <Label v-if="field.label" class="mb-1 block text-sm font-medium">{{ field.label }}</Label>
                    <div v-html="String(field.default || '').replace(/<\?xml.*\?>/g, '')"
                        class="rounded-lg border-2 border-dashed p-6 flex justify-center bg-muted shadow-inner min-h-[240px] items-center [&>svg]:block [&>svg]:max-w-full [&>svg]:h-auto" />
                </template>
                <template v-else-if="field.fieldtype === 'Check'">
                    <div class="flex items-center space-x-2 py-1">
                        <input type="checkbox" :id="field.fieldname" v-model="formValues[field.fieldname]"
                            class="size-4 rounded border-border text-primary focus:ring-primary" />
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

        <!-- Progress -->
        <div v-else-if="state.type === 'progress'" class="space-y-2 py-2">
            <div class="w-full h-2.5 bg-muted rounded-full overflow-hidden">
                <div class="h-full bg-primary rounded-full transition-all duration-300"
                    :style="{ width: `${state.progress.percent}%` }" />
            </div>
            <div class="flex items-center justify-between text-xs text-muted-foreground">
                <span v-if="state.progress.description">{{ state.progress.description }}</span>
                <span class="tabular-nums ml-auto">{{ state.progress.percent }}%</span>
            </div>
        </div>
    </div>

    <!-- Unified Footer -->
    <template #footer v-if="state.type !== 'progress'">
        <template v-if="state.type === 'msgprint'">
            <Button @click="close()">OK</Button>
        </template>
        <template v-else-if="state.type === 'confirm'">
            <Button outlined @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">Підтвердити</Button>
        </template>
        <template v-else-if="state.type === 'prompt'">
            <Button outlined @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">OK</Button>
        </template>
        <template v-else-if="state.type === 'dialog'">
            <Button outlined @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">{{ state.primaryLabel }}</Button>
        </template>
    </template>
  </Dialog>
</template>
