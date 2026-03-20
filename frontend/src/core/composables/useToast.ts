import { ref } from 'vue'

export interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'info'
}

const toasts = ref<Toast[]>([])

function add(message: string, type: Toast['type']) {
  const id = Math.random().toString(36).slice(2)
  toasts.value.push({ id, message, type })
  setTimeout(() => remove(id), 4_000)
}

function remove(id: string) {
  const i = toasts.value.findIndex(t => t.id === id)
  if (i > -1) toasts.value.splice(i, 1)
}

export function useToast() {
  return {
    toasts,
    remove,
    success: (message: string) => add(message, 'success'),
    error: (message: string) => add(message, 'error'),
    info: (message: string) => add(message, 'info'),
  }
}
