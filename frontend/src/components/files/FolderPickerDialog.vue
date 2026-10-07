<script setup lang="ts">
/**
 * «Upload to…» - the app-wide folder picker (see useFolderPicker): a
 * FileExplorer in folder mode inside a dialog. The files go to the selected
 * subfolder, else to the open one.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFolderPicker } from '@/core/composables/useFolderPicker'
import { formatFileSize } from '@/core/fileUtils'
import FileExplorer from '@/components/files/FileExplorer.vue'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const { t } = useI18n()
const { state, close } = useFolderPicker()

const target = ref<{ folder: string; title: string } | null>(null)
const totalSize = computed(() => state.files.reduce((sum, f) => sum + f.size, 0))

function onOpenChange(value: boolean) {
  if (!value) close(null)
}
</script>

<template>
  <Dialog :open="state.open" @update:open="onOpenChange">
    <DialogContent class="flex h-[min(640px,88vh)] flex-col gap-0 p-0 sm:max-w-4xl">
      <DialogHeader class="px-4 pt-4 pb-3">
        <DialogTitle>{{ t('Upload files') }}</DialogTitle>
        <DialogDescription class="truncate">
          <template v-if="state.files.length === 1">{{ state.files[0].name }} · {{ formatFileSize(totalSize) }}</template>
          <template v-else-if="state.files.length">
            {{ t('Files: {n}', { n: state.files.length }) }} · {{ formatFileSize(totalSize) }}
            — {{ state.files.slice(0, 3).map((f) => f.name).join(', ') }}{{ state.files.length > 3 ? '…' : '' }}
          </template>
          <template v-else>{{ t('Choose a folder') }}</template>
        </DialogDescription>
      </DialogHeader>

      <FileExplorer v-if="state.open" mode="folder" :folder="state.folder" :incoming-size="totalSize" :uploads="false"
        @update:target="(folder, title) => target = { folder, title }">
        <template #footer>
          <Button variant="outline" @click="close(null)">{{ t('Cancel') }}</Button>
          <Button :disabled="!target" @click="target && close(target.folder)">
            {{ t('Upload to «{name}»', { name: target?.title ?? '' }) }}
          </Button>
        </template>
      </FileExplorer>
    </DialogContent>
  </Dialog>
</template>
