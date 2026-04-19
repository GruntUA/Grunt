<script setup lang="ts">
import { useI18n } from 'vue-i18n'

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
    <Dialog
      :visible="showDelete"
      :modal="true"
      :closable="false"
      :style="{ width: '400px' }"
      @update:visible="emit('update:showDelete', $event)"
    >
      <template #header>
        <span class="font-semibold text-base">{{ t('Delete document?') }}</span>
      </template>
      <p class="text-sm text-muted-foreground">Цю дію не можна скасувати. Всі пов'язані дані будуть видалені назавжди.</p>
      <template #footer>
        <Button severity="secondary" text @click="emit('update:showDelete', false)">{{ t('Cancel') }}</Button>
        <Button severity="danger" @click="emit('confirmDelete')">{{ t('Delete') }}</Button>
      </template>
    </Dialog>

    <!-- Unsaved leave confirmation -->
    <Dialog
      :visible="showLeave"
      :modal="true"
      :closable="false"
      :style="{ width: '400px' }"
      @update:visible="emit('update:showLeave', $event)"
    >
      <template #header>
        <span class="font-semibold text-base">{{ t('Unsaved changes') }}</span>
      </template>
      <p class="text-sm text-muted-foreground">Ви внесли зміни, які буде втрачено, якщо ви покинете сторінку. Покинути без збереження?</p>
      <template #footer>
        <Button severity="secondary" text @click="emit('cancelLeave')">{{ t('Stay') }}</Button>
        <Button severity="danger" @click="emit('confirmLeave')">{{ t('Leave') }}</Button>
      </template>
    </Dialog>
  </div>
</template>
