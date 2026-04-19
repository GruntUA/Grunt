<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  pages: number
  total: number
  perPage: number
}>()

const emit = defineEmits<{
  'update:page': [value: number]
}>()

const onPageChange = (event: any) => {
    // PrimeVue page is 0-indexed
    emit('update:page', event.page + 1)
}

const first = computed(() => (props.page - 1) * props.perPage)
</script>

<template>
  <div class="flex items-center justify-between w-full py-2 px-1">
    <!-- Summary info -->
    <div class="hidden md:flex items-center gap-2">
        <span class="text-xs font-bold text-muted-foreground/60 uppercase tracking-widest">Всього:</span>
        <Badge severity="secondary" class="!text-[10px] !font-black !px-2 !py-0.5 shadow-sm">
            {{ total }}
        </Badge>
    </div>

    <!-- Paginator -->
    <div class="flex-1 flex justify-center md:justify-end">
        <Paginator 
            :rows="perPage" 
            :totalRecords="total" 
            :first="first"
            @page="onPageChange"
            template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink JumpToPageInput"
            class="!bg-transparent !p-0 !border-0"
            :pt="{
                root: { class: 'gap-1' },
                firstPageButton: { class: '!size-9 !rounded-xl transition-all' },
                previousPageButton: { class: '!size-9 !rounded-xl transition-all' },
                nextPageButton: { class: '!size-9 !rounded-xl transition-all' },
                lastPageButton: { class: '!size-9 !rounded-xl transition-all' },
                pageButton: ({ context }) => ({
                    class: [
                        '!size-9 !rounded-xl !text-xs !font-bold transition-all',
                        context.active ? '!bg-primary !text-primary-foreground !shadow-lg !shadow-primary/20' : '!bg-muted/30 !text-muted-foreground hover:!bg-muted/50'
                    ]
                }),
                pcJumpToPageInput: {
                    root: { class: '!h-9 !w-16' },
                    pcInput: { class: '!text-xs !font-bold !text-center' }
                }
            }"
        />
    </div>

    <!-- Mobile view summary -->
    <div class="md:hidden ml-4">
        <p class="text-[10px] font-black text-muted-foreground uppercase opacity-60">
            {{ page }} / {{ pages }}
        </p>
    </div>
  </div>
</template>

<style scoped>
:deep(.p-paginator) {
    justify-content: flex-end;
}

:deep(.p-paginator-page-selected) {
    background: var(--p-primary-color) !important;
    color: var(--p-primary-contrast-color) !important;
}

:deep(.p-paginator-element) {
    min-width: 2.25rem !important;
    height: 2.25rem !important;
}
</style>
