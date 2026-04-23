import { useShortcut } from '@/core/composables/useShortcuts'

interface UseFormShortcutsParams {
  onSave: () => void
  onPrint?: () => void
}

export function useFormShortcuts(params: UseFormShortcutsParams) {
  useShortcut(
    ['ctrl+s', 'cmd+s'],
    () => {
      params.onSave()
    },
    { preventDefault: true, allowInInput: true },
  )

  useShortcut(
    ['ctrl+p', 'cmd+p'],
    () => {
      if (params.onPrint) {
        params.onPrint()
        return
      }
      window.print()
    },
    { preventDefault: true, allowInInput: true },
  )
}
