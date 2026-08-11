<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

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
    <Dialog :open="showDelete" @update:open="emit('update:showDelete', $event)">
      <DialogContent class="w-[400px]" :show-close-button="false">
        <DialogHeader>
          <DialogTitle class="text-base">{{ t('Delete document?') }}</DialogTitle>
        </DialogHeader>
        <p class="text-sm text-muted-foreground">Цю дію не можна скасувати. Всі пов'язані дані будуть видалені назавжди.</p>
        <DialogFooter>
          <Button variant="ghost" @click="emit('update:showDelete', false)">{{ t('Cancel') }}</Button>
          <Button variant="destructive" @click="emit('confirmDelete')">{{ t('Delete') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Unsaved leave confirmation -->
    <Dialog :open="showLeave" @update:open="emit('update:showLeave', $event)">
      <DialogContent class="w-[400px]" :show-close-button="false">
        <DialogHeader>
          <DialogTitle class="text-base">{{ t('Unsaved changes') }}</DialogTitle>
        </DialogHeader>
        <p class="text-sm text-muted-foreground">Ви внесли зміни, які буде втрачено, якщо ви покинете сторінку. Покинути без збереження?</p>
        <DialogFooter>
          <Button variant="ghost" @click="emit('cancelLeave')">{{ t('Stay') }}</Button>
          <Button variant="destructive" @click="emit('confirmLeave')">{{ t('Leave') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
