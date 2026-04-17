<script setup lang="ts">
import { useId } from "vue"
import { Label } from "@/components/ui/label"

defineProps<{
  label?: string
  error?: string
  hint?: string
  required?: boolean
}>(

)

const id = useId()

defineExpose({ id })
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <Label v-if="label" :for="id" class="text-sm font-medium">
      {{ label }}<span v-if="required" class="text-destructive ml-0.5">*</span>
    </Label>
    <div :class="error ? 'ring-1 ring-destructive rounded-md' : ''">
      <slot :id="id" />
    </div>
    <p v-if="error" class="text-xs text-destructive">{{ error }}</p>
    <p v-else-if="hint" class="text-xs text-muted-foreground">{{ hint }}</p>
  </div>
</template>
