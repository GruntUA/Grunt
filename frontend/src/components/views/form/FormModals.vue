<script setup lang="ts">
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

defineProps<{
  showDelete: boolean
  showLeave: boolean
}>()

const emit = defineEmits<{
  (e: 'update:showDelete', val: boolean): void
  (e: 'update:showLeave', val: boolean): void
  (e: 'confirmDelete'): void
  (e: 'confirmLeave'): void
  (e: 'cancelLeave'): void
}>()
</script>

<template>
  <div>
    <!-- Delete confirmation -->
    <AlertDialog :open="showDelete" @update:open="emit('update:showDelete', $event)">
      <AlertDialogContent class="max-w-[400px]">
        <AlertDialogHeader>
          <AlertDialogTitle>Видалити документ?</AlertDialogTitle>
          <AlertDialogDescription>Цю дію не можна скасувати. Всі пов'язані дані будуть видалені назавжди.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="emit('update:showDelete', false)">Скасувати</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm"
            @click="emit('confirmDelete')">Видалити</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Unsaved leave confirmation -->
    <AlertDialog :open="showLeave" @update:open="emit('update:showLeave', $event)">
      <AlertDialogContent class="max-w-[400px]">
        <AlertDialogHeader>
          <AlertDialogTitle>Є незбережені зміни</AlertDialogTitle>
          <AlertDialogDescription>Ви внесли зміни, які буде втрачено, якщо ви покинете сторінку. Покинути без збереження?</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="emit('cancelLeave')">Залишитись</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm"
            @click="emit('confirmLeave')">Покинути</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
