import { useToast as usePvToast } from 'primevue/usetoast'

let globalToast: any = null

export function useToast() {
  const pvToast = usePvToast()
  if (pvToast) globalToast = pvToast

  return {
    success: (message: string, summary = 'Успіх', opts?: any) => 
      (pvToast || globalToast)?.add({ severity: 'success', summary, detail: message, life: 3000, ...opts }),
    error: (message: string, summary = 'Помилка', opts?: any) => 
      (pvToast || globalToast)?.add({ severity: 'error', summary, detail: message, life: 5000, ...opts }),
    info: (message: string, summary = 'Інформація', opts?: any) => 
      (pvToast || globalToast)?.add({ severity: 'info', summary, detail: message, life: 3000, ...opts }),
    warning: (message: string, summary = 'Увага', opts?: any) => 
      (pvToast || globalToast)?.add({ severity: 'warn', summary, detail: message, life: 4000, ...opts }),
    removeGroup: (group: string) => (pvToast || globalToast)?.removeGroup(group),
  }
}

/** 
 * Non-composable version for plain JS files. 
 * Requires useToast() to have been called at least once in a component.
 */
export const toast = {
  success: (m: string, s?: string, o?: any) => globalToast?.add({ severity: 'success', summary: s ?? 'Успіх', detail: m, life: 3000, ...o }),
  error: (m: string, s?: string, o?: any) => globalToast?.add({ severity: 'error', summary: s ?? 'Помилка', detail: m, life: 5000, ...o }),
  info: (m: string, s?: string, o?: any) => globalToast?.add({ severity: 'info', summary: s ?? 'Інформація', detail: m, life: 3000, ...o }),
  warning: (m: string, s?: string, o?: any) => globalToast?.add({ severity: 'warn', summary: s ?? 'Увага', detail: m, life: 4000, ...o }),
  removeGroup: (group: string) => globalToast?.removeGroup(group),
}

