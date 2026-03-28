<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog'
import { Trash2 } from 'lucide-vue-next'

defineProps<{
  count: number
}>()

const emit = defineEmits<{
  delete: []
  clear: []
}>()

const showModal = ref(false)
</script>

<template>
  <Transition name="bulk">
    <div v-if="count > 0" class="flex items-center gap-3 mb-3 px-4 py-2.5 bg-primary/5 rounded-lg border border-primary/20">
      <span class="text-sm text-primary font-medium">Вибрано: {{ count }}</span>
      <Button variant="destructive" size="sm" @click="showModal = true">
        <Trash2 class="size-3.5 mr-1" />
        Видалити
      </Button>
      <button type="button" class="text-sm text-muted-foreground hover:text-foreground ml-auto transition-colors" @click="emit('clear')">
        Скасувати
      </button>
    </div>
  </Transition>

  <AlertDialog :open="showModal" @update:open="showModal = $event">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>Видалити вибрані записи?</AlertDialogTitle>
        <AlertDialogDescription>Буде видалено {{ count }} записів. Цю дію не можна скасувати.</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>Скасувати</AlertDialogCancel>
        <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90" @click="showModal = false; emit('delete')">
          Видалити
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>

<style scoped>
.bulk-enter-active,
.bulk-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.bulk-enter-from,
.bulk-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
