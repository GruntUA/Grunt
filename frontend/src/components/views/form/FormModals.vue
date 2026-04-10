<script setup lang="ts">
import { useI18n } from 'vue-i18n'
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

const { t } = useI18n()

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
          <AlertDialogTitle>{{ t('Delete document?') }}</AlertDialogTitle>
          <AlertDialogDescription>Цю дію не можна скасувати. Всі пов'язані дані будуть видалені назавжди.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="emit('update:showDelete', false)">{{ t('Cancel') }}</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm"
            @click="emit('confirmDelete')">{{ t('Delete') }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Unsaved leave confirmation -->
    <AlertDialog :open="showLeave" @update:open="emit('update:showLeave', $event)">
      <AlertDialogContent class="max-w-[400px]">
        <AlertDialogHeader>
          <AlertDialogTitle>{{ t('Unsaved changes') }}</AlertDialogTitle>
          <AlertDialogDescription>Ви внесли зміни, які буде втрачено, якщо ви покинете сторінку. Покинути без збереження?</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="emit('cancelLeave')">{{ t('Stay') }}</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm"
            @click="emit('confirmLeave')">{{ t('Leave') }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
