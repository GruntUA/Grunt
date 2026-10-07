<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronDown, FileUp, Image as ImageIcon, Images, Loader2, Paperclip, Plus, Table as TableIcon, Trash2, Upload, Video,
} from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useToast } from '@/core/composables/useToast'
import { useRichEditorContext } from '../editor/useRichEditor'
import { watchUrl } from '../extensions/youtube'
import CommandMenuItem from './CommandMenuItem.vue'
import TableGridPicker from './TableGridPicker.vue'

// "+ Insert": media, file blocks, table, rule, Word import. Image and video
// ask for a URL in a popover anchored to this menu's button.
const { t } = useI18n()
const toast = useToast()
const { editor, uploading, uploadImage, insertFileBlock, importDocx } = useRichEditorContext()

const trigger = ref<{ $el: HTMLElement } | null>(null)
const menuOpen = ref(false)
const form = ref<'image' | 'video' | null>(null)
const url = ref('')
const docxInput = ref<HTMLInputElement | null>(null)

function openForm(kind: 'image' | 'video') {
  const e = editor.value
  url.value = kind === 'video' && e?.isActive('youtube') ? watchUrl(e.getAttributes('youtube').src ?? '') : ''
  form.value = kind
}

function submitForm() {
  const src = url.value.trim()
  const chain = editor.value?.chain().focus()
  if (src && form.value === 'image') chain?.setImage({ src }).run()
  if (src && form.value === 'video' && !chain?.setYoutubeVideo({ src }).run()) {
    toast.error(t('Paste a YouTube video link'), t('Invalid link'))
    return
  }
  form.value = null
}

function removeVideo() {
  editor.value?.chain().focus().deleteSelection().run()
  form.value = null
}

async function onImageFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file && await uploadImage(file)) form.value = null
}

function onDocxFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) importDocx(file)
}

function insertTable(rows: number, cols: number) {
  menuOpen.value = false
  editor.value?.chain().focus().insertTable({ rows, cols, withHeaderRow: true }).run()
}
</script>

<template>
  <Popover :open="!!form" @update:open="(v) => { if (!v) form = null }">
    <DropdownMenu v-model:open="menuOpen">
      <DropdownMenuTrigger as-child>
        <Button ref="trigger" size="sm" variant="ghost" class="gap-1 px-1.5" :aria-label="t('Insert')">
          <Loader2 v-if="uploading" class="animate-spin" />
          <Plus v-else />
          <span class="hidden @2xl:inline">{{ t('Insert') }}</span>
          <ChevronDown class="hidden size-3 opacity-60 @2xl:block" />
        </Button>
      </DropdownMenuTrigger>
      <!-- No refocus on close: the image / video popover takes focus next. -->
      <DropdownMenuContent align="start" class="w-56" @close-auto-focus.prevent>
        <DropdownMenuItem @select="openForm('image')"><ImageIcon /> {{ t('Image') }}…</DropdownMenuItem>
        <DropdownMenuItem @select="openForm('video')"><Video /> {{ t('YouTube video') }}…</DropdownMenuItem>
        <DropdownMenuItem @select="insertFileBlock('fileList')"><Paperclip /> {{ t('Files') }}…</DropdownMenuItem>
        <DropdownMenuItem @select="insertFileBlock('gallery')"><Images /> {{ t('Gallery') }}…</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger :disabled="editor?.isActive('table')"><TableIcon /> {{ t('Table') }}</DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <TableGridPicker @pick="insertTable" />
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <CommandMenuItem id="details" />
        <CommandMenuItem id="horizontalRule" />
        <DropdownMenuSeparator />
        <DropdownMenuItem :disabled="uploading" @select="docxInput?.click()"><FileUp /> {{ t('Import from Word (.docx)') }}…</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>

    <!-- Anchored by element: an as-child PopoverAnchor around the menu trigger doesn't resolve. -->
    <PopoverAnchor :reference="trigger?.$el" />
    <PopoverContent align="start" class="w-80 p-2">
      <p class="mb-2 font-medium text-muted-foreground">{{ form === 'image' ? t('Image') : t('YouTube video') }}</p>
      <div class="flex gap-2">
        <Input
          v-model="url" class="h-8 flex-1"
          :placeholder="form === 'image' ? 'https://…' : 'https://www.youtube.com/watch?v=…'"
          :aria-label="form === 'image' ? t('Image URL') : t('Video URL')"
          @keydown.enter.prevent="submitForm"
        />
        <Button size="sm" @click="submitForm">OK</Button>
        <Button
          v-if="form === 'video' && editor?.isActive('youtube')" size="icon-sm" variant="ghost"
          class="text-destructive hover:text-destructive" :title="t('Remove video')" :aria-label="t('Remove video')"
          @click="removeVideo"
        >
          <Trash2 />
        </Button>
      </div>
      <label
        v-if="form === 'image'"
        class="mt-2 flex cursor-pointer items-center gap-2 rounded p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Upload class="size-3.5" />
        <span>{{ uploading ? t('Uploading…') : t('Upload file') }}</span>
        <input type="file" accept="image/*" class="hidden" :disabled="uploading" @change="onImageFile" />
      </label>
    </PopoverContent>
  </Popover>
  <input ref="docxInput" type="file" accept=".docx" class="hidden" @change="onDocxFile" />
</template>
