/**
 * «Where to upload» - an Explorer-style folder picker over the personal file
 * spaces (FileFolder). One dialog for the whole app, mounted in App.vue:
 *
 * ```ts
 * const folder = await useFolderPicker().pick({ files, folder: current })
 * if (folder) upload(files, folder)
 * ```
 */
import { reactive } from 'vue'

export interface FolderPickerOptions {
  /** The files about to be uploaded - shown in the header. */
  files?: File[]
  /** The folder to open first; «My files» when omitted. */
  folder?: string | null
}

interface FolderPickerState {
  open: boolean
  files: File[]
  folder: string | null
  resolve: ((folder: string | null) => void) | null
}

const state = reactive<FolderPickerState>({ open: false, files: [], folder: null, resolve: null })

export function useFolderPicker() {
  function pick(opts: FolderPickerOptions = {}): Promise<string | null> {
    state.resolve?.(null)
    return new Promise((resolve) => {
      Object.assign(state, { open: true, files: opts.files ?? [], folder: opts.folder ?? null, resolve })
    })
  }

  function close(folder: string | null) {
    const resolve = state.resolve
    Object.assign(state, { open: false, resolve: null })
    resolve?.(folder)
  }

  return { state, pick, close }
}

/**
 * Cut / Copy in the file explorers - one clipboard for the whole app, so a
 * file copied in one dialog can be pasted in the next.
 */
export const fileClipboard = reactive<{
  mode: 'cut' | 'copy' | null
  files: string[]
  folders: string[]
}>({ mode: null, files: [], folders: [] })
