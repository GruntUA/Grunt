<script setup lang="ts">
import type { DocField } from '@/types'
import { Button } from '@/components/ui/button'

const props = defineProps<{
    field: DocField
    modelValue: unknown
    disabled?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

function onClick() {
    emit('update:modelValue', Date.now())
}
</script>

<template>
    <div class="py-1">
        <Button type="button" variant="secondary" :disabled="disabled || field.read_only" class="w-full sm:w-auto"
            @click="onClick">
            {{ field.label }}
        </Button>
    </div>
</template>
