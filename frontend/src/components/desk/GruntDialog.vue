<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDialog } from '@/core/composables/useDialog'
import LinkField from '@/components/fields/Link/Link.vue'

const { state, close } = useDialog()
const promptValue = ref('')
const formValues = ref<Record<string, any>>({})
const copiedField = ref<string | null>(null)

async function copyToClipboard(fieldname: string, value: string) {
  try {
    await navigator.clipboard.writeText(value)
    copiedField.value = fieldname
    setTimeout(() => { copiedField.value = null }, 2000)
  } catch {
    // fallback: select text in the textarea
  }
}

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
  <Dialog :open="state.open" @update:open="(v: boolean) => { state.open = v; if (!v) onOpenChange(false) }">
    <DialogContent class="sm:max-w-md p-0 px-6 pb-4 pt-2">
    <DialogHeader v-if="state.title">
      <DialogTitle class="font-semibold flex items-center gap-2">
        <span v-if="state.indicator" class="inline-block w-2.5 h-2.5 rounded-full shrink-0"
          :style="{ backgroundColor: state.indicator }" />
        {{ state.title }}
      </DialogTitle>
    </DialogHeader>
    <DialogTitle v-else class="sr-only">Діалог</DialogTitle>

    <!-- Content -->
    <div>
        <!-- Msgprint -->
        <div v-if="state.type === 'msgprint'" class="text-sm text-foreground leading-relaxed whitespace-pre-wrap py-2" v-html="state.message" />

        <!-- Confirm -->
        <p v-else-if="state.type === 'confirm'" class="text-sm text-muted-foreground py-2">{{ state.message }}</p>

        <!-- Prompt -->
        <div v-else-if="state.type === 'prompt'" class="space-y-2 py-2">
            <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
                <label :for="field.fieldname" class="text-sm font-medium">{{ field.label }}</label>
                <div v-if="field.fieldtype === 'HTML'" v-html="field.default" class="rounded border p-2 bg-muted/30" />
                <Input v-else :id="field.fieldname" v-model="promptValue" :placeholder="field.placeholder"
                    :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
                    class="w-full"
                    @keydown.enter="onConfirm" />
            </div>
        </div>

        <!-- Custom Dialog (grunt.form) -->
        <div v-else-if="state.type === 'dialog'" class="space-y-4 py-2">
            <div v-for="field in state.fields" :key="field.fieldname" class="space-y-2">
                <template v-if="field.fieldtype === 'HTML'">
                    <label v-if="field.label" class="mb-1 block text-sm font-medium">{{ field.label }}</label>
                    <div v-html="String(field.default || '').replace(/<\?xml.*\?>/g, '')"
                        class="rounded-lg border-2 border-dashed p-6 flex justify-center bg-muted shadow-inner min-h-[240px] items-center [&>svg]:block [&>svg]:max-w-full [&>svg]:h-auto" />
                </template>
                <template v-else-if="field.fieldtype === 'Check'">
                    <div class="flex items-center space-x-2 py-1">
                        <Checkbox :id="field.fieldname" v-model="formValues[field.fieldname]" />
                        <label :for="field.fieldname" class="cursor-pointer text-sm">{{ field.label }}</label>
                    </div>
                </template>
                <template v-else-if="field.fieldtype === 'LongText' || field.fieldtype === 'Code'">
                    <div class="flex items-center justify-between gap-2">
                        <label :for="field.fieldname" class="text-sm font-medium">{{ field.label }}</label>
                        <button
                            v-if="field.read_only"
                            type="button"
                            class="shrink-0 text-xs px-2 py-0.5 rounded border border-border text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
                            @click="copyToClipboard(field.fieldname, String(formValues[field.fieldname] ?? ''))"
                        >
                            {{ copiedField === field.fieldname ? 'Скопійовано ✓' : 'Копіювати' }}
                        </button>
                    </div>
                    <p v-if="field.description" class="text-xs text-muted-foreground -mt-1">{{ field.description }}</p>
                    <textarea
                        :id="field.fieldname"
                        v-model="formValues[field.fieldname]"
                        :readonly="field.read_only"
                        rows="12"
                        :class="[
                            'w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none',
                            field.fieldtype === 'Code' ? 'font-mono' : '',
                            field.read_only ? 'bg-muted/40 cursor-default' : '',
                        ]"
                    />
                </template>
                <template v-else-if="field.fieldtype === 'Link'">
                    <label :for="field.fieldname" class="text-sm font-medium">{{ field.label }}</label>
                    <p v-if="field.description" class="text-xs text-muted-foreground -mt-1">{{ field.description }}</p>
                    <LinkField
                        :field="{ fieldname: field.fieldname, fieldtype: 'Link', options: field.options, label: field.label }"
                        :model-value="formValues[field.fieldname]"
                        @update:model-value="formValues[field.fieldname] = $event"
                        @create-new="() => {}"
                    />
                </template>
                <template v-else>
                    <label :for="field.fieldname" class="text-sm font-medium">{{ field.label }}</label>
                    <p v-if="field.description" class="text-xs text-muted-foreground -mt-1">{{ field.description }}</p>
                    <Input :id="field.fieldname" v-model="formValues[field.fieldname]" :placeholder="field.placeholder"
                        :type="field.fieldtype === 'Int' || field.fieldtype === 'Float' ? 'number' : 'text'"
                        class="w-full"
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
    <DialogFooter v-if="state.type !== 'progress'">
        <template v-if="state.type === 'msgprint'">
            <Button @click="close()">OK</Button>
        </template>
        <template v-else-if="state.type === 'confirm'">
            <Button variant="outline" @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">Підтвердити</Button>
        </template>
        <template v-else-if="state.type === 'prompt'">
            <Button variant="outline" @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">OK</Button>
        </template>
        <template v-else-if="state.type === 'dialog'">
            <Button variant="outline" @click="onCancel">Скасувати</Button>
            <Button @click="onConfirm">{{ state.primaryLabel }}</Button>
        </template>
    </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
