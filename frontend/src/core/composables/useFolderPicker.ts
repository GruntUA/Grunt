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
  /** The folder to open first; the last one opened (else «My files») when omitted. */
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
 * The folder the user last opened in any file explorer - the next one starts
 * there instead of «My files». Per user, in this browser.
 */
const LAST_FOLDER_KEY = 'grunt_last_folder:'

export function lastFolder(user: string): string | null {
  try {
    return localStorage.getItem(LAST_FOLDER_KEY + user)
  } catch {
    return null
  }
}

export function rememberFolder(user: string, folder: string | null): void {
  try {
    if (folder) localStorage.setItem(LAST_FOLDER_KEY + user, folder)
    else localStorage.removeItem(LAST_FOLDER_KEY + user)
  } catch {
    // best-effort, like the other UI memories
  }
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
