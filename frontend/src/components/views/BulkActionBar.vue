<script setup lang="ts">
import { ref, computed } from 'vue'
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
import { Trash2, X } from 'lucide-vue-next'

const props = defineProps<{
  count: number
  total?: number
  allSelected?: boolean
  pageCount?: number
}>()

const emit = defineEmits<{
  (e: 'delete'): void
  (e: 'clear'): void
  (e: 'selectAll'): void
}>()

const showModal = ref(false)

const isFullPage = computed(() =>
  !props.allSelected && props.pageCount != null && props.count >= props.pageCount && props.count > 0
)

const displayCount = computed(() =>
  props.allSelected && props.total ? props.total : props.count
)
</script>

<template>
  <div v-if="count > 0 || allSelected" class="flex items-center gap-3 mb-3 px-4 py-2.5 bg-primary/5 rounded-lg border border-primary/20">
    <span class="text-sm text-primary font-medium">
      Вибрано: {{ allSelected ? `всі ${total ?? ''}` : count }}
    </span>

    <button
      v-if="isFullPage && total && total > count"
      type="button"
      class="text-sm text-primary underline hover:text-primary/80 transition-colors"
      @click="emit('selectAll')"
    >
      Обрати всі {{ total }} документів
    </button>

    <Button variant="destructive" size="sm" @click="showModal = true">
      <Trash2 class="size-3.5 mr-1" />
      Видалити{{ allSelected ? ' всі' : '' }}
    </Button>

    <button type="button" class="ml-auto text-muted-foreground hover:text-foreground transition-colors" @click="emit('clear')">
      <X class="size-4" />
    </button>

    <AlertDialog :open="showModal" @update:open="showModal = $event">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Видалити вибрані записи?</AlertDialogTitle>
          <AlertDialogDescription>
            Буде видалено {{ displayCount }} записів. Цю дію не можна скасувати.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Скасувати</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            @click="showModal = false; emit('delete')"
          >
            Видалити
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
