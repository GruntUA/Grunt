import { toast as sonnerToast } from 'vue-sonner'
import i18n from '@/plugins/i18n'

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
  // Errors and warnings get a Copy button - their text goes into bug reports.
  const action = severity === 'error' || severity === 'warning'
    ? { label: i18n.global.t('Copy'), onClick: () => copyText(message ? `${summary}: ${message}` : summary) }
    : undefined
  const id = sonnerToast[severity](summary, { description: message, duration: life, action, ...rest })
  if (group) groupIds.set(group, id)
  return id
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // No Clipboard API (plain http) - the old selection trick still works.
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    area.remove()
  }
  sonnerToast.success(i18n.global.t('Copied'), { duration: 1500 })
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
    success: (message: string, summary = i18n.global.t('Success'), opts?: any) => show('success', message, summary, { life: 3000, ...opts }),
    error: (message: string, summary = i18n.global.t('Error'), opts?: any) => show('error', message, summary, { life: 5000, ...opts }),
    info: (message: string, summary = i18n.global.t('Info'), opts?: any) => show('info', message, summary, { life: 3000, ...opts }),
    warning: (message: string, summary = i18n.global.t('Warning'), opts?: any) => show('warning', message, summary, { life: 4000, ...opts }),
    removeGroup,
  }
}

/**
 * Non-composable version for plain JS files.
 * Works anywhere - sonner's `toast()` has no Vue-context dependency, unlike PrimeVue's useToast().
 */
export const toast = {
  success: (m: string, s?: string, o?: any) => show('success', m, s ?? i18n.global.t('Success'), { life: 3000, ...o }),
  error: (m: string, s?: string, o?: any) => show('error', m, s ?? i18n.global.t('Error'), { life: 5000, ...o }),
  info: (m: string, s?: string, o?: any) => show('info', m, s ?? i18n.global.t('Info'), { life: 3000, ...o }),
  warning: (m: string, s?: string, o?: any) => show('warning', m, s ?? i18n.global.t('Warning'), { life: 4000, ...o }),
  removeGroup,
}
