<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ellipsis, ExternalLink, ImagePlus, ImageUp, Trash2, Upload } from '@lucide/vue'
import { filesApi } from '@/core/api/files'
import { useToast } from '@/core/composables/useToast'
import { useDialog } from '@/core/composables/useDialog'
import type { AttachmentResult } from '@/components/fields/Attach/attachment'
import AttachPicker from '@/components/fields/Attach/AttachPicker.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia } from '@/components/ui/empty'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const props = defineProps<{
  /** Current value of the DocType's `image_field` (the form's, so unsaved picks show up). */
  url: string | null
  /** Upload / replace / remove allowed (write permission, field not read-only). */
  editable: boolean
  doctype: string
  /** Missing for a new document - the file is uploaded unattached. */
  docId?: string
  alt?: string
}>()

const emit = defineEmits<{ change: [url: string | null] }>()

const { t } = useI18n()
const toast = useToast()
const dialog = useDialog()

const pickerOpen = ref(false)
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function onPick(result: AttachmentResult) {
  emit('change', result.url)
}

async function upload(file: File) {
  if (!file.type.startsWith('image/')) {
    toast.error(t('Only images can be used here'))
    return
  }
  uploading.value = true
  try {
    const item = await filesApi.upload(file, { attachedToDoctype: props.doctype, attachedToId: props.docId })
    emit('change', item.url)
  } catch {
    toast.error(t('Could not upload the image'))
  } finally {
    uploading.value = false
  }
}

function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) void upload(file)
}

// Drag & drop (drop onto the image replaces it)
function onDragOver(e: DragEvent) {
  if (!props.editable || uploading.value || !e.dataTransfer?.types.includes('Files')) return
  e.preventDefault()
  dragOver.value = true
}
function onDrop(e: DragEvent) {
  dragOver.value = false
  if (!props.editable || uploading.value) return
  const file = e.dataTransfer?.files[0]
  if (!file) return
  e.preventDefault()
  void upload(file)
}

async function remove() {
  if (await dialog.confirm(t('Remove the image from the document?'))) emit('change', null)
}
</script>

<template>
  <div
    v-if="url || editable"
    @dragover="onDragOver"
    @dragleave="dragOver = false"
    @drop="onDrop"
  >
    <!-- Image -->
    <AspectRatio v-if="url" :ratio="16 / 9" class="group overflow-hidden rounded-md border bg-muted/40">
      <img :src="url" :alt="alt ?? ''" class="size-full object-contain" />

      <DropdownMenu v-if="editable">
        <DropdownMenuTrigger as-child>
          <Button
            variant="secondary"
            size="icon-sm"
            class="absolute top-2 right-2 size-7 shadow-sm opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(hover:none)]:opacity-100"
            :aria-label="t('Image actions')"
            :disabled="uploading"
          >
            <Ellipsis />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-52">
          <DropdownMenuItem @select="pickerOpen = true">
            <ImageUp />
            {{ t('Replace image') }}
          </DropdownMenuItem>
          <DropdownMenuItem @select="fileInput?.click()">
            <Upload />
            {{ t('Upload from computer') }}
          </DropdownMenuItem>
          <DropdownMenuItem as="a" :href="url" target="_blank" rel="noopener">
            <ExternalLink />
            {{ t('Open in new tab') }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" @select="remove">
            <Trash2 />
            {{ t('Remove image') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <div
        v-if="uploading || dragOver"
        class="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/80 text-sm font-medium backdrop-blur-[2px]"
        :class="dragOver && 'border-2 border-dashed border-primary rounded-md text-primary'"
      >
        <Spinner v-if="uploading" />
        <template v-else>
          <ImageUp class="size-5" />
          {{ t('Drop to replace') }}
        </template>
      </div>
    </AspectRatio>

    <!-- Empty: add an image -->
    <Empty
      v-else
      class="gap-3 border p-4 md:p-4 transition-colors"
      :class="dragOver && 'border-primary bg-primary/5'"
    >
      <EmptyHeader class="gap-1">
        <EmptyMedia variant="icon" class="mb-1 size-9">
          <Spinner v-if="uploading" />
          <ImagePlus v-else class="size-5" />
        </EmptyMedia>
        <EmptyDescription class="text-xs">{{ t('Drop a file or click to choose') }}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" size="sm" :disabled="uploading" @click="pickerOpen = true">
          <ImagePlus />
          {{ t('Add image') }}
        </Button>
      </EmptyContent>
    </Empty>

    <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFileInput" />

    <AttachPicker
      v-if="editable"
      v-model:open="pickerOpen"
      :image-only="true"
      :current-url="url"
      @select="onPick"
    />
  </div>
</template>
