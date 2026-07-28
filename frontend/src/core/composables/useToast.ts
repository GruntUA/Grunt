import { toast as sonnerToast } from 'vue-sonner'

// Tracks the last toast id shown per "group" so a later call can dismiss it
// (replicates PrimeVue's removeGroup, e.g. a persistent "offline" notice).
const groupIds = new Map<string, string | number>()

function show(
  severity: 'success' | 'error' | 'info' | 'warning',
  message: string,
  summary: string,
  opts?: { life?: number; group?: string } & Record<string, unknown>,
) {
  const { life, group, ...rest } = opts ?? {}
  const id = sonnerToast[severity](summary, { description: message, duration: life, ...rest })
  if (group) groupIds.set(group, id)
  return id
}

function removeGroup(group: string) {
  const id = groupIds.get(group)
  if (id !== undefined) {
    sonnerToast.dismiss(id)
    groupIds.delete(group)
  }
}

export function useToast() {
  return {
    success: (message: string, summary = 'Успіх', opts?: any) => show('success', message, summary, { life: 3000, ...opts }),
    error: (message: string, summary = 'Помилка', opts?: any) => show('error', message, summary, { life: 5000, ...opts }),
    info: (message: string, summary = 'Інформація', opts?: any) => show('info', message, summary, { life: 3000, ...opts }),
    warning: (message: string, summary = 'Увага', opts?: any) => show('warning', message, summary, { life: 4000, ...opts }),
    removeGroup,
  }
}

/**
 * Non-composable version for plain JS files.
 * Works anywhere — sonner's `toast()` has no Vue-context dependency, unlike PrimeVue's useToast().
 */
export const toast = {
  success: (m: string, s?: string, o?: any) => show('success', m, s ?? 'Успіх', { life: 3000, ...o }),
  error: (m: string, s?: string, o?: any) => show('error', m, s ?? 'Помилка', { life: 5000, ...o }),
  info: (m: string, s?: string, o?: any) => show('info', m, s ?? 'Інформація', { life: 3000, ...o }),
  warning: (m: string, s?: string, o?: any) => show('warning', m, s ?? 'Увага', { life: 4000, ...o }),
  removeGroup,
}
